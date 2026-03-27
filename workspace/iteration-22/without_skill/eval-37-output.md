# GKE 1.31 → 1.32 Upgrade Plan for AI/ML Platform

## Pre-Upgrade Assessment & Preparation

### Infrastructure Audit
```yaml
# Current Fleet Status
clusters:
  training-cluster:
    nodes: 2000
    type: H100
    priority: CRITICAL
    workloads: Training jobs, experiments
  
  inference-cluster:
    nodes: 1500
    type: A100
    priority: HIGH
    workloads: Production inference, serving
  
  dev-cluster:
    nodes: 500
    type: T4
    priority: MEDIUM
    workloads: Development, testing
  
  services-cluster:
    nodes: 1000
    type: CPU
    priority: HIGH
    workloads: Platform services, monitoring
```

### Pre-Flight Checklist
```bash
# 1. Backup critical data
kubectl get all --all-namespaces -o yaml > pre-upgrade-backup.yaml

# 2. Validate workload compatibility
kubectl api-versions > current-api-versions.txt

# 3. Check deprecated APIs
kubectl get --raw /metrics | grep deprecated

# 4. Verify addon compatibility
gcloud container clusters describe $CLUSTER_NAME --format="yaml(addonsConfig)"
```

## Phase 1: Development Environment (Week 1)
**Target: T4 Development Nodes (500 nodes)**

### Phase 1A: Control Plane Upgrade
```bash
# Upgrade control plane first
gcloud container clusters upgrade dev-cluster \
    --master \
    --cluster-version=1.32.0-gke.1200 \
    --zone=$ZONE
```

### Phase 1B: Node Pool Upgrade (25% increments)
```bash
# Create upgrade script
cat << 'EOF' > upgrade-dev-nodes.sh
#!/bin/bash
CLUSTER="dev-cluster"
NODE_POOL="dev-t4-pool"
BATCH_SIZE=125  # 25% of 500 nodes

for i in {1..4}; do
    echo "Upgrading batch $i of dev nodes..."
    
    # Cordon and drain nodes
    kubectl get nodes -l node-pool=$NODE_POOL | head -n $BATCH_SIZE | \
    while read node; do
        kubectl cordon $node
        kubectl drain $node --ignore-daemonsets --delete-emptydir-data --force
    done
    
    # Upgrade batch
    gcloud container clusters upgrade $CLUSTER \
        --node-pool=$NODE_POOL \
        --cluster-version=1.32.0-gke.1200 \
        --max-surge-upgrade=25 \
        --max-unavailable-upgrade=0
    
    # Verify batch health
    sleep 300
    kubectl get nodes | grep Ready | wc -l
done
EOF

chmod +x upgrade-dev-nodes.sh
./upgrade-dev-nodes.sh
```

## Phase 2: Services Infrastructure (Week 2)
**Target: CPU Service Nodes (1,000 nodes)**

### Phase 2A: Prepare Service Redundancy
```yaml
# Increase replica counts for critical services
apiVersion: v1
kind: ConfigMap
metadata:
  name: service-scaling-config
data:
  pre-upgrade-scaling.yaml: |
    services:
      monitoring:
        replicas: 6  # increased from 3
      ingress-controller:
        replicas: 4  # increased from 2
      dns:
        replicas: 6  # increased from 3
      logging:
        replicas: 4  # increased from 2
```

### Phase 2B: Rolling Service Upgrade
```bash
# Services upgrade with enhanced monitoring
cat << 'EOF' > upgrade-services.sh
#!/bin/bash
CLUSTER="services-cluster"
BATCH_SIZE=200  # 20% batches for services

# Pre-upgrade health check
kubectl get pods --all-namespaces | grep -E "(Error|CrashLoop|Pending)"

for batch in {1..5}; do
    echo "Upgrading services batch $batch..."
    
    # Scale up critical services before upgrade
    kubectl scale deployment monitoring-stack --replicas=6
    kubectl scale deployment ingress-nginx --replicas=4
    
    # Upgrade control plane
    if [ $batch -eq 1 ]; then
        gcloud container clusters upgrade $CLUSTER --master \
            --cluster-version=1.32.0-gke.1200
    fi
    
    # Upgrade node batch
    gcloud container operations wait $(
        gcloud container clusters upgrade $CLUSTER \
            --node-pool=services-pool \
            --cluster-version=1.32.0-gke.1200 \
            --max-surge-upgrade=20 \
            --max-unavailable-upgrade=10 \
            --format="value(name)"
    )
    
    # Health verification
    sleep 180
    kubectl get pods --all-namespaces | grep -v Running | grep -v Completed
    
done
EOF

./upgrade-services.sh
```

## Phase 3: Inference Infrastructure (Week 3-4)
**Target: A100 Inference Nodes (1,500 nodes)**

### Phase 3A: Traffic Management Setup
```yaml
# Implement traffic shifting
apiVersion: v1
kind: Service
metadata:
  name: inference-service-canary
spec:
  selector:
    app: inference
    version: upgraded
  ports:
  - port: 8080
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: inference-traffic-split
spec:
  http:
  - match:
    - headers:
        canary:
          exact: "true"
    route:
    - destination:
        host: inference-service-canary
  - route:
    - destination:
        host: inference-service
      weight: 90
    - destination:
        host: inference-service-canary
      weight: 10
```

### Phase 3B: Inference Cluster Upgrade
```bash
cat << 'EOF' > upgrade-inference.sh
#!/bin/bash
CLUSTER="inference-cluster"
TOTAL_NODES=1500
BATCH_SIZE=150  # 10% batches for inference

# Create monitoring dashboard
kubectl apply -f - << 'YAML'
apiVersion: v1
kind: ConfigMap
metadata:
  name: inference-monitoring
data:
  alerts.yaml: |
    groups:
    - name: inference-upgrade
      rules:
      - alert: InferenceLatencyHigh
        expr: inference_request_duration_seconds{quantile="0.95"} > 2
      - alert: InferenceErrorRateHigh
        expr: rate(inference_errors_total[5m]) > 0.01
YAML

for batch in {1..10}; do
    echo "=== Upgrading inference batch $batch/10 ==="
    
    # Pre-batch validation
    echo "Current inference capacity:"
    kubectl get nodes -l node-type=inference | grep Ready | wc -l
    
    # Gradual traffic shift to remaining nodes
    kubectl patch virtualservice inference-traffic-split --type='json' \
        -p="[{'op': 'replace', 'path': '/spec/http/1/route/0/weight', 'value': $((90 + batch))}]"
    
    # Control plane upgrade (first batch only)
    if [ $batch -eq 1 ]; then
        echo "Upgrading control plane..."
        gcloud container clusters upgrade $CLUSTER --master \
            --cluster-version=1.32.0-gke.1200 --async
        
        # Wait for control plane
        while ! kubectl get nodes > /dev/null 2>&1; do
            sleep 30
        done
    fi
    
    # Node upgrade with careful batching
    echo "Upgrading $BATCH_SIZE nodes in batch $batch..."
    
    # Get nodes for this batch
    NODES=$(kubectl get nodes -l node-type=inference --no-headers | \
            awk '{print $1}' | head -n $BATCH_SIZE)
    
    # Cordon nodes
    echo $NODES | xargs -n1 kubectl cordon
    
    # Gracefully drain workloads
    for node in $NODES; do
        kubectl drain $node \
            --ignore-daemonsets \
            --delete-emptydir-data \
            --grace-period=300 \
            --timeout=600s &
    done
    wait
    
    # Perform upgrade
    gcloud container clusters upgrade $CLUSTER \
        --node-pool=inference-a100-pool \
        --cluster-version=1.32.0-gke.1200 \
        --max-surge-upgrade=10 \
        --max-unavailable-upgrade=5
    
    # Verify batch completion
    echo "Waiting for nodes to be ready..."
    for node in $NODES; do
        kubectl wait --for=condition=Ready node/$node --timeout=600s
    done
    
    # Health check
    kubectl get pods -n inference | grep -E "(Error|CrashLoop|Pending)"
    
    # Restore traffic gradually
    sleep 300  # 5-minute stability check
    
    echo "Batch $batch completed successfully"
done

# Final traffic restoration
kubectl patch virtualservice inference-traffic-split --type='json' \
    -p="[{'op': 'replace', 'path': '/spec/http/1/route/0/weight', 'value': 100}]"

echo "Inference cluster upgrade completed!"
EOF

./upgrade-inference.sh
```

## Phase 4: Training Infrastructure (Week 5-6)
**Target: H100 Training Nodes (2,000 nodes)**

### Phase 4A: Training Job Management
```yaml
# Training job coordination
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-coordinator
spec:
  template:
    spec:
      containers:
      - name: coordinator
        image: training-coordinator:latest
        env:
        - name: CHECKPOINT_FREQUENCY
          value: "15min"  # Increased frequency during upgrade
        - name: UPGRADE_MODE
          value: "true"
        command:
        - /bin/bash
        - -c
        - |
          # Force checkpoint of all running training jobs
          kubectl get jobs -l type=training --no-headers | \
          while read job; do
            kubectl annotate job/$job upgrade.kubernetes.io/checkpoint="true"
            # Send SIGUSR1 to trigger checkpoint
            kubectl exec -l job-name=$job -- pkill -USR1 python
          done
```

### Phase 4B: Training Cluster Upgrade
```bash
cat << 'EOF' > upgrade-training.sh
#!/bin/bash
CLUSTER="training-cluster"
TOTAL_NODES=2000
BATCH_SIZE=100  # 5% batches for training (most conservative)

echo "=== Starting Training Cluster Upgrade ==="
echo "Total nodes: $TOTAL_NODES"
echo "Batch size: $BATCH_SIZE"
echo "Total batches: $((TOTAL_NODES / BATCH_SIZE))"

# Pre-upgrade preparations
echo "Preparing training environment for upgrade..."

# Increase checkpoint frequency
kubectl patch configmap training-config --patch '
{
  "data": {
    "checkpoint_interval": "900",
    "upgrade_mode": "true"
  }
}'

# Create upgrade monitoring
kubectl apply -f - << 'YAML'
apiVersion: v1
kind: Service
metadata:
  name: upgrade-monitor
  labels:
    app: upgrade-monitor
spec:
  ports:
  - port: 8080
    name: metrics
  selector:
    app: upgrade-monitor
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: upgrade-monitor
spec:
  replicas: 1
  selector:
    matchLabels:
      app: upgrade-monitor
  template:
    metadata:
      labels:
        app: upgrade-monitor
    spec:
      containers:
      - name: monitor
        image: prom/prometheus:latest
        ports:
        - containerPort: 8080
YAML

for batch in {1..20}; do
    echo ""
    echo "=== TRAINING BATCH $batch/20 ==="
    echo "$(date): Starting batch $batch"
    
    # Control plane upgrade (first batch only)
    if [ $batch -eq 1 ]; then
        echo "Upgrading training cluster control plane..."
        gcloud container clusters upgrade $CLUSTER \
            --master \
            --cluster-version=1.32.0-gke.1200 \
            --zone=$ZONE
        
        echo "Control plane upgrade completed"
    fi
    
    # Get current training jobs
    echo "Active training jobs before batch $batch:"
    kubectl get jobs -l type=training --no-headers | wc -l
    
    # Select nodes for this batch
    NODES=$(kubectl get nodes -l node-type=training \
            -o jsonpath='{.items[*].metadata.name}' | \
            tr ' ' '\n' | head -n $BATCH_SIZE)
    
    echo "Selected $BATCH_SIZE nodes for batch $batch"
    
    # Trigger checkpoints for jobs on these nodes
    echo "Triggering checkpoints for affected jobs..."
    for node in $NODES; do
        PODS=$(kubectl get pods --field-selector spec.nodeName=$node \
               -l type=training -o jsonpath='{.items[*].metadata.name}')
        
        for pod in $PODS; do
            echo "Checkpointing job on pod $pod"
            kubectl exec $pod -- python -c "
import signal, os
os.kill(os.getpid(), signal.SIGUSR1)  # Trigger checkpoint
" || true
        done
    done
    
    # Wait for checkpoints to complete
    echo "Waiting for checkpoints to complete..."
    sleep 600  # 10 minutes for checkpoint completion
    
    # Cordon nodes
    echo "Cordoning nodes in batch $batch..."
    for node in $NODES; do
        kubectl cordon $node
    done
    
    # Gracefully terminate training jobs on these nodes
    echo "Gracefully draining training workloads..."
    for node in $NODES; do
        echo "Draining node $node..."
        kubectl drain $node \
            --ignore-daemonsets \
            --delete-emptydir-data \
            --grace-period=600 \
            --timeout=900s \
            --force &
    done
    
    # Wait for all drains to complete
    wait
    echo "All nodes in batch $batch drained successfully"
    
    # Perform the actual upgrade
    echo "Upgrading nodes in batch $batch..."
    gcloud container clusters upgrade $CLUSTER \
        --node-pool=training-h100-pool \
        --cluster-version=1.32.0-gke.1200 \
        --max-surge-upgrade=5 \
        --max-unavailable-upgrade=0 \
        --zone=$ZONE
    
    # Wait for nodes to be ready
    echo "Waiting for upgraded nodes to be ready..."
    for node in $NODES; do
        kubectl wait --for=condition=Ready node/$node --timeout=1200s
    done
    
    # Uncordon nodes
    for node in $NODES; do
        kubectl uncordon $node
    done
    
    # Verify node health
    echo "Verifying node health for batch $batch..."
    kubectl get nodes | grep -E "NotReady|SchedulingDisabled" || echo "All nodes healthy"
    
    # Allow training jobs to reschedule
    echo "Batch $batch upgrade completed. Waiting for job rescheduling..."
    sleep 300  # 5-minute buffer between batches
    
    # Monitor job recovery
    echo "Training jobs after batch $batch:"
    kubectl get jobs -l type=training --no-headers | wc -l
    
    echo "$(date): Batch $batch completed successfully"
    echo "Nodes remaining: $((TOTAL_NODES - (batch * BATCH_SIZE)))"
done

# Post-upgrade cleanup
echo ""
echo "=== POST-UPGRADE CLEANUP ==="

# Restore normal checkpoint frequency
kubectl patch configmap training-config --patch '
{
  "data": {
    "checkpoint_interval": "3600",
    "upgrade_mode": "false"
  }
}'

# Verify all nodes are ready
echo "Final node status:"