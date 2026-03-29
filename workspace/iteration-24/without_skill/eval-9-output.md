With 600 nodes, your upgrade bottleneck is likely the default surge configuration. Here are several strategies to dramatically reduce upgrade time:

## 1. Optimize Surge Settings (Biggest Impact)

Increase the surge capacity for faster parallel upgrades:

```bash
# For CPU pools - be more aggressive
gcloud container node-pools update CPU-POOL-1 \
    --cluster=your-cluster \
    --zone=your-zone \
    --max-surge=20 \
    --max-unavailable=10

# For GPU pools - more conservative due to cost/availability
gcloud container node-pools update GPU-POOL-1 \
    --cluster=your-cluster \
    --zone=your-zone \
    --max-surge=5 \
    --max-unavailable=2
```

## 2. Staggered Pool Strategy

Upgrade pools in sequence to maximize resource utilization:

```bash
#!/bin/bash
# Weekend upgrade script

# Start with one CPU pool (highest surge)
gcloud container node-pools update cpu-pool-1 --async

# Monitor and start GPU pool when CPU is 50% complete
# ... monitoring logic ...

gcloud container node-pools update gpu-pool-1 --async
```

## 3. Pre-pull Images

Reduce node startup time by pre-pulling critical images:

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: image-prepull
spec:
  selector:
    matchLabels:
      name: image-prepull
  template:
    spec:
      initContainers:
      - name: prepull
        image: your-critical-app:latest
        command: ['sh', '-c', 'echo "Image pulled"']
      containers:
      - name: sleep
        image: gcr.io/google-containers/pause:3.1
```

## 4. Split Large Node Pools

Consider breaking down large pools for parallel upgrades:

```bash
# Instead of 1 pool with 300 CPU nodes, create 2 pools with 150 each
gcloud container node-pools create cpu-pool-1a \
    --cluster=your-cluster \
    --num-nodes=75 \
    --max-surge=15

gcloud container node-pools create cpu-pool-1b \
    --cluster=your-cluster \
    --num-nodes=75 \
    --max-surge=15
```

## 5. Optimize Pod Disruption Budgets

Ensure PDBs aren't blocking node drains:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 80%  # Instead of maxUnavailable: 1
  selector:
    matchLabels:
      app: your-app
```

## 6. Use Regional Persistent Disks

Speed up pod rescheduling across zones:

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-regional-ssd
provisioner: kubernetes.io/gce-pd
parameters:
  type: pd-ssd
  replication-type: regional-pd
```

## 7. Monitor and Tune

Track upgrade progress and bottlenecks:

```bash
# Monitor upgrade status
watch 'kubectl get nodes -o wide | grep -E "(Ready|NotReady|SchedulingDisabled)"'

# Check for stuck pods
kubectl get pods --all-namespaces --field-selector=status.phase=Pending
```

## Expected Timeline Improvement

With these optimizations:
- **Before**: 24+ hours
- **After**: 6-8 hours (within your maintenance window)

The surge settings alone should reduce your upgrade time by 60-70%. Start with increasing max-surge to 15-20 for CPU pools and 5-8 for GPU pools, then adjust based on your specific workload tolerance and budget constraints.

Would you like me to help you calculate the optimal surge settings based on your specific node pool sizes and workload requirements?