This is a challenging scenario that requires careful orchestration. Here's a comprehensive strategy to upgrade your GKE cluster without disrupting your active training run:

## Pre-Upgrade Assessment

First, verify your current setup and constraints:

```bash
# Check current cluster configuration
kubectl get nodes -l cloud.google.com/gke-accelerator=nvidia-h100-80gb
kubectl describe nodes | grep -E "(Kernel Version|Container Runtime|Kubelet Version)"

# Verify GPUDirect-TCPXO status
kubectl get pods -A -o wide | grep tcpxo
kubectl logs -n kube-system daemonset/nvidia-device-plugin-daemonset
```

## Strategy 1: Blue-Green Node Pool Migration (Recommended)

### Step 1: Create New Node Pool with GKE 1.32

```yaml
# new-nodepool-config.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-strategy
data:
  strategy: "blue-green"
---
```

```bash
# Create new node pool with 1.32
gcloud container node-pools create h100-v132-pool \
    --cluster=your-training-cluster \
    --zone=your-zone \
    --machine-type=a3-megagpu-8g \
    --accelerator=type=nvidia-h100-80gb,count=8 \
    --num-nodes=0 \
    --enable-autoscaling \
    --min-nodes=0 \
    --max-nodes=64 \
    --node-version=1.32.x-gke.xxxx \
    --enable-gvnic \
    --placement-type=COMPACT \
    --network-performance-config=total-egress-bandwidth-tier=TIER_1 \
    --shielded-secure-boot \
    --shielded-integrity-monitoring \
    --enable-ip-alias \
    --disk-type=pd-ssd \
    --disk-size=200GB \
    --metadata=enable-oslogin=true \
    --node-taints=training.ai/new-pool=true:NoSchedule
```

### Step 2: Prepare Training Job for Migration

Add node affinity and anti-affinity rules to your training workload:

```yaml
# training-job-migration.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: llm-training-migration
spec:
  template:
    spec:
      affinity:
        nodeAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            nodeSelectorTerms:
            - matchExpressions:
              - key: cloud.google.com/gke-nodepool
                operator: In
                values: ["h100-v131-pool", "h100-v132-pool"]  # Allow both pools
              - key: cloud.google.com/gke-accelerator
                operator: In
                values: ["nvidia-h100-80gb"]
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
          - labelSelector:
              matchExpressions:
              - key: job-name
                operator: In
                values: ["llm-training-migration"]
            topologyKey: kubernetes.io/hostname
      tolerations:
      - key: training.ai/new-pool
        operator: Equal
        value: "true"
        effect: NoSchedule
      - key: nvidia.com/gpu
        operator: Exists
        effect: NoSchedule
      containers:
      - name: training-container
        # Your existing container spec
        env:
        - name: NCCL_NET_GDR_LEVEL
          value: "PIX"
        - name: NCCL_P2P_LEVEL
          value: "PIX"
        - name: NCCL_NET
          value: "GPUDirectTCPX_v7"
```

### Step 3: Implement Checkpoint-Based Migration

Create a migration controller that handles checkpointing:

```python
# checkpoint-migration-controller.py
import kubernetes
import time
import subprocess
import os

class TrainingMigrationController:
    def __init__(self):
        kubernetes.config.load_incluster_config()
        self.k8s_client = kubernetes.client.ApiClient()
        self.batch_v1 = kubernetes.client.BatchV1Api()
        
    def trigger_checkpoint(self, job_name, namespace="default"):
        """Trigger checkpoint via SIGUSR1"""
        pods = self.get_training_pods(job_name, namespace)
        
        for pod in pods:
            # Send checkpoint signal
            command = ['kubectl', 'exec', pod.metadata.name, 
                      '--', 'kill', '-USR1', '1']
            subprocess.run(command, check=True)
            
        # Wait for checkpoint completion
        self.wait_for_checkpoint_completion(job_name, namespace)
    
    def wait_for_checkpoint_completion(self, job_name, namespace):
        """Wait for all pods to complete checkpointing"""
        timeout = 1800  # 30 minutes
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.all_pods_checkpointed(job_name, namespace):
                return True
            time.sleep(30)
            
        raise TimeoutError("Checkpoint timeout")
    
    def scale_new_nodepool(self, nodepool_name, target_nodes):
        """Scale up new node pool"""
        cmd = [
            'gcloud', 'container', 'clusters', 'resize', 
            'your-training-cluster', '--node-pool', nodepool_name,
            '--num-nodes', str(target_nodes), '--zone', 'your-zone'
        ]
        subprocess.run(cmd, check=True)
```

### Step 4: Execute Rolling Migration

```bash
#!/bin/bash
# migration-script.sh

set -e

CLUSTER_NAME="your-training-cluster"
ZONE="your-zone"
OLD_POOL="h100-v131-pool"
NEW_POOL="h100-v132-pool"
NODES_PER_BATCH=8  # Migrate 8 nodes at a time

echo "Starting migration from $OLD_POOL to $NEW_POOL"

# Function to wait for nodes to be ready
wait_for_nodes_ready() {
    local pool=$1
    local expected_count=$2
    
    echo "Waiting for $expected_count nodes in pool $pool to be ready..."
    
    while true; do
        ready_count=$(kubectl get nodes -l cloud.google.com/gke-nodepool=$pool \
                     --no-headers | grep " Ready " | wc -l)
        
        if [ "$ready_count" -eq "$expected_count" ]; then
            echo "All $expected_count nodes in pool $pool are ready"
            break
        fi
        
        echo "Ready nodes: $ready_count/$expected_count. Waiting..."
        sleep 30
    done
}

# Function to migrate batch of nodes
migrate_batch() {
    local batch_size=$1
    local batch_num=$2
    
    echo "=== Migrating batch $batch_num (size: $batch_size) ==="
    
    # 1. Scale up new pool
    echo "Scaling up new pool..."
    gcloud container clusters resize $CLUSTER_NAME \
        --node-pool $NEW_POOL \
        --num-nodes $((batch_num * batch_size)) \
        --zone $ZONE \
        --quiet
    
    # 2. Wait for new nodes
    wait_for_nodes_ready $NEW_POOL $((batch_num * batch_size))
    
    # 3. Trigger checkpoint
    echo "Triggering checkpoint..."
    python3 checkpoint-migration-controller.py trigger-checkpoint
    
    # 4. Drain old nodes from this batch
    echo "Draining old nodes..."
    kubectl get nodes -l cloud.google.com/gke-nodepool=$OLD_POOL \
        --no-headers | head -n $batch_size | awk '{print $1}' | \
    while read node; do
        kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force &
    done
    wait
    
    # 5. Remove taint from new nodes to allow scheduling
    kubectl get nodes -l cloud.google.com/gke-nodepool=$NEW_POOL \
        --no-headers | tail -n $batch_size | awk '{print $1}' | \
    while read node; do
        kubectl taint nodes $node training.ai/new-pool-
    done
    
    # 6. Wait for training to reschedule and stabilize
    echo "Waiting for training to stabilize..."
    sleep 300  # 5 minutes
    
    # 7. Scale down old pool
    current_old_nodes=$(kubectl get nodes -l cloud.google.com/gke-nodepool=$OLD_POOL --no-headers | wc -l)
    new_old_count=$((current_old_nodes - batch_size))
    
    if [ $new_old_count -gt 0 ]; then
        gcloud container clusters resize $CLUSTER_NAME \
            --node-pool $OLD_POOL \
            --num-nodes $new_old_count \
            --zone $ZONE \
            --quiet
    fi
    
    echo "Batch $batch_num completed successfully"
}

# Execute migration in batches
TOTAL_NODES=64  # 512 GPUs / 8 GPUs per node
TOTAL_BATCHES=$((TOTAL_NODES / NODES_PER_BATCH))

for batch in $(seq 1 $TOTAL_BATCHES); do
    migrate_batch $NODES_PER_BATCH $batch
    echo "Completed batch $batch/$TOTAL_BATCHES"
done

echo "Migration completed successfully!"
```

## Strategy 2: In-Place Node Pool Upgrade (Alternative)

If blue-green is not feasible due to quota constraints:

```bash
# Upgrade node pool in-place with surge settings
gcloud container node-pools update h100-pool \
    --cluster=your-training-cluster \
    --zone=your-zone \
    --max-surge-upgrade=8 \
    --max-unavailable-upgrade=0 \
    --node-version=1.32.x-gke.xxxx
```

## Critical Considerations

### 1. GPUDirect-TCPXO Preservation

```yaml
# Ensure GPUDirect configuration persists
apiVersion: v1
kind: ConfigMap
metadata:
  name: tcpxo-config
  namespace: kube-system
data:
  config.yaml: |
    networking:
      tcpxo:
        enabled: true
        version: "v7"
        bandwidth_tier: "TIER_1"
```

### 2. Monitoring During Migration

```bash
# Monitor training job health
kubectl top pods -l app=llm-training --containers
kubectl logs -f deployment/llm-training -c training-container | grep -E "(loss|checkpoint|error)"

# Monitor GPU utilization
kubectl get --raw /api/v1/nodes/NODE_NAME/proxy/metrics/resource | grep gpu
```

### 3. Rollback Plan

```bash
# Emergency rollback script
#!/bin/bash
kubectl patch job llm-training -p '{"spec":{"suspend":true}}'
kubectl scale deployment training-job --replicas=0
# Restore from last checkpoint
kubectl apply -f training-job-rollback.yaml
```

## Post-Migration Validation

```bash
# Validate cluster health
kubectl get nodes
kubectl get pods -A | grep -E "(Pending|Error|CrashLoop)"

# Validate GPUDirect-TCPXO
kubectl exec -it training-pod -- nvidia-smi topo -m
kubectl exec -it training-pod -- ibv_devinfo

# Validate training performance
kubectl logs training-pod | grep "samples/sec\|tokens/sec\|training_loss"
```

This approach minimizes downtime by migrating in small batches while maintaining GPU interconnect topology and allowing your training job to checkpoint and resume gracefully across the upgrade.