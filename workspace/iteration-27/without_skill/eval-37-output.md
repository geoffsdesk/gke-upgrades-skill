# GKE Fleet Upgrade Plan: v1.31 → v1.32
## Mixed AI/ML Platform (5,000 Nodes)

## 🎯 **Upgrade Priorities**
1. **Training Continuity** - Minimize disruption to H100 training workloads
2. **Inference Availability** - Maintain A100 inference SLA
3. **Development Flexibility** - Quick T4 upgrades for testing
4. **Service Stability** - Gradual CPU node transitions

---

## 📋 **Pre-Upgrade Preparation**

### Control Plane Upgrade
```bash
# Upgrade control plane first (minimal downtime)
gcloud container clusters upgrade ml-cluster \
    --master \
    --cluster-version=1.32.0-gke.1200 \
    --zone=us-central1-a
```

### Backup & Validation
```bash
# Backup critical workloads
kubectl get all --all-namespaces -o yaml > pre-upgrade-backup.yaml

# Validate node pool configurations
kubectl get nodes -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion,INSTANCE:.spec.providerID
```

---

## 🚀 **Phase 1: Development & Testing (Week 1)**
**Target: 500 T4 Development Nodes**

### 1.1 Create Canary T4 Pool (Day 1)
```bash
# Create small canary pool for testing
gcloud container node-pools create t4-dev-canary-132 \
    --cluster=ml-cluster \
    --machine-type=n1-standard-4 \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --num-nodes=10 \
    --node-version=1.32.0-gke.1200 \
    --node-labels=env=dev,gpu=t4,upgrade=canary \
    --node-taints=upgrade=canary:NoSchedule
```

### 1.2 Validate Canary (Days 2-3)
```yaml
# Test deployment for validation
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ml-validation-t4
spec:
  replicas: 5
  selector:
    matchLabels:
      app: ml-validation
  template:
    spec:
      nodeSelector:
        upgrade: canary
      tolerations:
      - key: upgrade
        value: canary
        effect: NoSchedule
      containers:
      - name: gpu-test
        image: tensorflow/tensorflow:2.14.0-gpu
        resources:
          limits:
            nvidia.com/gpu: 1
```

### 1.3 Rolling Upgrade T4 Pools (Days 4-7)
```bash
# Upgrade T4 development pools in batches
for pool in t4-dev-pool-{1..5}; do
    echo "Upgrading $pool..."
    gcloud container node-pools upgrade $pool \
        --cluster=ml-cluster \
        --node-version=1.32.0-gke.1200 \
        --max-surge-upgrade=2 \
        --max-unavailable-upgrade=1
    
    # Wait and validate before next pool
    sleep 300
done
```

---

## 🔧 **Phase 2: CPU Service Nodes (Week 2)**
**Target: 1,000 CPU Nodes**

### 2.1 Service Dependency Mapping
```bash
# Identify critical services
kubectl get pods -o wide --all-namespaces | grep -E "(monitoring|logging|ingress|dns)"

# Create service availability dashboard
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-monitoring
data:
  services.yaml: |
    critical_services:
    - kube-dns
    - ingress-nginx
    - prometheus
    - grafana
    - logging-agent
EOF
```

### 2.2 Staged CPU Node Upgrade
```bash
# Upgrade CPU nodes in 25% increments
NODE_POOLS=(cpu-pool-1 cpu-pool-2 cpu-pool-3 cpu-pool-4)

for i in "${!NODE_POOLS[@]}"; do
    pool=${NODE_POOLS[$i]}
    echo "Upgrading CPU pool $((i+1))/4: $pool"
    
    # Cordon nodes before upgrade
    kubectl get nodes -l node-pool=$pool -o name | xargs kubectl cordon
    
    # Upgrade with careful surge settings
    gcloud container node-pools upgrade $pool \
        --cluster=ml-cluster \
        --node-version=1.32.0-gke.1200 \
        --max-surge-upgrade=3 \
        --max-unavailable-upgrade=1
    
    # Validate services after each pool
    kubectl get pods -n kube-system | grep -E "(Ready|Running)"
    sleep 600  # 10-minute stabilization
done
```

---

## ⚡ **Phase 3: A100 Inference Nodes (Week 3-4)**
**Target: 1,500 A100 GPU Nodes**

### 3.1 Inference Load Balancing Setup
```yaml
# Configure inference traffic distribution
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: inference-lb
  annotations:
    nginx.ingress.kubernetes.io/upstream-hash-by: "$request_uri"
spec:
  rules:
  - host: inference.ml-platform.com
    http:
      paths:
      - path: /v1/models
        pathType: Prefix
        backend:
          service:
            name: inference-service
            port:
              number: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: inference-service
spec:
  selector:
    app: ml-inference
    gpu: a100
  ports:
  - port: 8080
    targetPort: 8080
  sessionAffinity: ClientIP
```

### 3.2 Blue-Green Inference Upgrade
```bash
# Create green A100 pool
gcloud container node-pools create a100-inference-green-132 \
    --cluster=ml-cluster \
    --machine-type=a2-highgpu-4g \
    --accelerator=type=nvidia-tesla-a100,count=4 \
    --num-nodes=375 \
    --node-version=1.32.0-gke.1200 \
    --node-labels=env=inference,gpu=a100,pool=green \
    --preemptible=false

# Deploy inference workloads to green pool
kubectl patch deployment ml-inference \
    -p '{"spec":{"template":{"spec":{"nodeSelector":{"pool":"green"}}}}}'

# Monitor inference metrics
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: inference-monitor
spec:
  selector:
    app: ml-inference
  ports:
  - name: metrics
    port: 9090
    targetPort: 9090
EOF
```

### 3.3 Traffic Migration & Validation
```bash
# Gradual traffic shift (10%, 50%, 100%)
for weight in 10 50 100; do
    echo "Shifting ${weight}% traffic to green pool..."
    
    kubectl annotate ingress inference-lb \
        nginx.ingress.kubernetes.io/canary-weight="$weight"
    
    # Monitor for 30 minutes
    echo "Monitoring inference latency and error rates..."
    sleep 1800
    
    # Validate metrics
    kubectl exec -n monitoring prometheus-0 -- \
        promtool query instant 'avg(inference_latency_seconds)' | \
        awk '{if($1 > 0.5) exit 1}'
done

# Remove blue pool after validation
gcloud container node-pools delete a100-inference-blue \
    --cluster=ml-cluster --quiet
```

---

## 🧠 **Phase 4: H100 Training Nodes (Week 5-6)**
**Target: 2,000 H100 GPU Nodes**

### 4.1 Training Job Checkpoint Strategy
```yaml
# Enhanced checkpoint configuration
apiVersion: batch/v1
kind: Job
metadata:
  name: training-checkpoint-manager
spec:
  template:
    spec:
      containers:
      - name: checkpoint-sync
        image: gcr.io/ml-platform/checkpoint-manager:latest
        env:
        - name: CHECKPOINT_INTERVAL
          value: "300"  # 5 minutes
        - name: GCS_BUCKET
          value: "gs://ml-platform-checkpoints"
        volumeMounts:
        - name: checkpoint-storage
          mountPath: /checkpoints
      volumes:
      - name: checkpoint-storage
        persistentVolumeClaim:
          claimName: training-checkpoints
```

### 4.2 Training Pool Upgrade Strategy
```bash
# Identify long-running training jobs
kubectl get jobs -l gpu=h100 --sort-by=.status.startTime

# Create maintenance windows
TRAINING_POOLS=(h100-training-{1..10})

for pool in "${TRAINING_POOLS[@]}"; do
    echo "Preparing $pool for upgrade..."
    
    # Signal checkpoint and pause to training jobs
    kubectl annotate jobs -l node-pool=$pool \
        ml-platform.com/maintenance="checkpoint-and-pause"
    
    # Wait for jobs to checkpoint (30 minutes)
    echo "Waiting for training jobs to checkpoint..."
    sleep 1800
    
    # Upgrade pool with minimal disruption
    gcloud container node-pools upgrade $pool \
        --cluster=ml-cluster \
        --node-version=1.32.0-gke.1200 \
        --max-surge-upgrade=1 \
        --max-unavailable-upgrade=1
    
    # Resume training jobs
    kubectl annotate jobs -l node-pool=$pool \
        ml-platform.com/maintenance-
    
    echo "$pool upgrade complete. Waiting 2 hours before next pool..."
    sleep 7200
done
```

### 4.3 Training Validation & Optimization
```bash
# Validate H100 utilization post-upgrade
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: gpu-monitor
spec:
  selector:
    matchLabels:
      name: gpu-monitor
  template:
    metadata:
      labels:
        name: gpu-monitor
    spec:
      nodeSelector:
        gpu: h100
      containers:
      - name: nvidia-smi
        image: nvidia/cuda:12.2-runtime-ubuntu20.04
        command: ["nvidia-smi", "dmon", "-s", "puct", "-d", "30"]
        resources:
          limits:
            nvidia.com/gpu: 0
EOF
```

---

## 📊 **Monitoring & Rollback Strategy**

### Real-time Monitoring Dashboard
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: upgrade-dashboard
data:
  dashboard.json: |
    {
      "dashboard": {
        "title": "GKE Upgrade Progress",
        "panels": [
          {
            "title": "Node Version Distribution",
            "type": "piechart",
            "targets": [
              {
                "expr": "count by (kubelet_version) (kube_node_info)"
              }
            ]
          },
          {
            "title": "Training Job Status",
            "type": "stat",
            "targets": [
              {
                "expr": "sum by (status) (kube_job_status_active{gpu=\"h100\"})"
              }
            ]
          },
          {
            "title": "Inference Latency",
            "type": "graph",
            "targets": [
              {
                "expr": "histogram_quantile(0.95, inference_request_duration_seconds_bucket)"
              }
            ]
          }
        ]
      }
    }
```

### Emergency Rollback Procedure
```bash
#!/bin/bash
# rollback.sh - Emergency rollback script

ROLLBACK_VERSION="1.31.8-gke.1000"

rollback_pool() {
    local pool_name=$1
    echo "Rolling back $pool_name to $ROLLBACK_VERSION"
    
    gcloud container node-pools upgrade $pool_name \
        --cluster=ml-cluster \
        --node-version=$ROLLBACK_VERSION \
        --max-surge-upgrade=5 \
        --max-unavailable-upgrade=2
}

# Rollback priority: Inference → Services → Training → Development
case $1 in
    "critical")
        rollback_pool "a100-inference-pool"
        rollback_pool "cpu-services-pool"
        ;;
    "full")
        for pool in $(gcloud container node-pools list --cluster=ml-cluster --format="value(name)"); do
            rollback_pool $pool
        done
        ;;
esac
```

---

## ✅ **Success Metrics & Validation**

### Key Performance Indicators
```bash
# Training continuity (target: >95%)
echo "Training uptime: $(kubectl get jobs -l gpu=h100 -o jsonpath='{.items[*].status.conditions[?(@.type=="Complete")].status}' | grep -c True) jobs completed"

# Inference availability (target: >99.9%)
echo "Inference SLA: $(curl -s http://monitoring/api/v1/query?query=up{job=\"inference\"} | jq '.data.result[0].value[1]')"

# Upgrade completion rate
kubectl get nodes -o custom-columns=VERSION:.status.nodeInfo.kubeletVersion --no-headers | sort | uniq -c
```

### Final Validation Checklist
- [ ] All 5,000 nodes running Kubernetes 1.32
- [ ] Training jobs resuming from checkpoints
- [ ] Inference latency within SLA
- [ ] GPU utilization metrics normal
- [ ] No critical alerts in monitoring
- [ ] Rollback procedures tested and documented

---

## 🎉 **Timeline Summary**
- **Week 1**: Development nodes (500 T4)
- **Week 2**: Service nodes (1,000 CPU)  
- **Week 3-4**: Inference nodes (1,500 A100)
- **Week 5-6**: Training nodes (2,000 H100)

**Total Duration**: 6 weeks with minimal disruption to ML workloads.

This phased approach ensures training continuity while maintaining inference availability throughout the upgrade process.