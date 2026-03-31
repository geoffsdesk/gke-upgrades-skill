# GKE Cluster Configuration for H100 Foundation Model Training

## Recommended Cluster Configuration

### Core Cluster Settings
```bash
gcloud container clusters create training-cluster \
  --zone us-central1-a \
  --release-channel extended \
  --cluster-version 1.31.3-gke.1146000 \
  --enable-ip-alias \
  --enable-network-policy \
  --enable-shielded-nodes \
  --workload-pool PROJECT_ID.svc.id.goog \
  --logging=SYSTEM,WORKLOAD \
  --monitoring=SYSTEM \
  --enable-autorepair \
  --enable-autoupgrade \
  --maintenance-window-start "2024-01-07T03:00:00Z" \
  --maintenance-window-duration 6h \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU" \
  --maintenance-patch-version-disruption-interval=7776000s \
  --addons HorizontalPodAutoscaling,HttpLoadBalancing \
  --max-nodes-per-pool 1000
```

### Training Node Pool (H100)
```bash
gcloud container node-pools create h100-training \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --num-nodes 8 \
  --enable-autorepair \
  --enable-autoupgrade \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --disk-size 200GB \
  --disk-type pd-ssd \
  --reservation-affinity any \
  --placement-type COMPACT \
  --node-taints=training-only=true:NoSchedule
```

### Inference/System Node Pool (separate pool for non-training workloads)
```bash
gcloud container node-pools create system-pool \
  --cluster training-cluster \
  --zone us-central1-a \
  --machine-type n2-standard-8 \
  --num-nodes 3 \
  --enable-autorepair \
  --enable-autoupgrade \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0 \
  --disk-size 100GB \
  --disk-type pd-standard
```

## Release Channel Strategy: Extended Channel

**Why Extended Channel:**
- **24-month support** for each version (vs 14 months on Regular/Stable)
- **NO automatic minor version upgrades** for control plane (except at end of extended support)
- **Patches auto-applied at Regular channel timing** — no delay on security updates
- **Maximum control** over disruptive changes while maintaining security posture
- **Cost only during extended period** (months 15-24) — no extra charge during standard support

## Maintenance Exclusions for Training Protection

```bash
# Apply "no minor or node upgrades" exclusion (persistent until EoS)
gcloud container clusters update training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
  --add-maintenance-exclusion-until-end-of-support
```

**This exclusion provides:**
- ✅ Control plane security patches auto-applied (critical for security compliance)
- ❌ Minor version upgrades blocked (prevents breaking changes during training)
- ❌ Node pool upgrades blocked (prevents training job interruption)
- 🔄 Tracks version EoS automatically — no need to chain exclusions

## Training Job Configuration

### Pod Template for Multi-Week Training
```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: foundation-model-training
spec:
  template:
    metadata:
      annotations:
        # Prevent eviction during node maintenance
        cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 3600  # 1 hour for checkpoint save
      tolerations:
      - key: training-only
        operator: Equal
        value: "true"
        effect: NoSchedule
      nodeSelector:
        cloud.google.com/gke-nodepool: h100-training
      containers:
      - name: trainer
        image: gcr.io/PROJECT_ID/training:latest
        resources:
          requests:
            nvidia.com/gpu: 8
            cpu: 96
            memory: 800Gi
          limits:
            nvidia.com/gpu: 8
        volumeMounts:
        - name: training-data
          mountPath: /data
        - name: checkpoints
          mountPath: /checkpoints
```

### PodDisruptionBudget for Training Jobs
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: 1
  selector:
    matchLabels:
      job-type: foundation-training
```

## Upgrade Strategy for H100 Pools

### GPU Pool Constraints
- **NO surge capacity available** — H100 reservations are fixed, no extra nodes for surge upgrades
- **maxUnavailable is the only effective lever** for GPU pools with fixed reservations
- **Every upgrade requires pod restart** — H100 VMs don't support live migration

### Recommended Settings Already Applied Above
```bash
--max-surge-upgrade 0           # No extra GPU nodes available
--max-unavailable-upgrade 1     # Drain one node at a time
```

### Training Campaign Workflow

**Before starting multi-week training:**
1. Verify maintenance exclusion is active:
   ```bash
   gcloud container clusters describe training-cluster \
     --zone us-central1-a \
     --format="value(maintenancePolicy.window)"
   ```

2. Enable checkpoint frequency (every 6-12 hours minimum):
   ```python
   # In training code
   if step % CHECKPOINT_INTERVAL == 0:
       save_checkpoint(model, optimizer, step, '/checkpoints/')
   ```

**During active training (exclusion protects automatically):**
- Control plane patches auto-apply during Sunday 3-9 AM window
- Node pool upgrades blocked by exclusion
- Training jobs protected from eviction

**Between training campaigns (planned upgrade windows):**
1. Remove exclusion temporarily:
   ```bash
   gcloud container clusters update training-cluster \
     --zone us-central1-a \
     --remove-maintenance-exclusion training-protection
   ```

2. Trigger manual upgrades if needed:
   ```bash
   # Upgrade control plane first
   gcloud container clusters upgrade training-cluster \
     --zone us-central1-a \
     --master \
     --cluster-version TARGET_VERSION

   # Then H100 node pool (when no training jobs running)
   gcloud container node-pools upgrade h100-training \
     --cluster training-cluster \
     --zone us-central1-a \
     --cluster-version TARGET_VERSION
   ```

3. Reapply exclusion:
   ```bash
   gcloud container clusters update training-cluster \
     --zone us-central1-a \
     --add-maintenance-exclusion-name "training-protection" \
     --add-maintenance-exclusion-scope no_minor_or_node_upgrades \
     --add-maintenance-exclusion-until-end-of-support
   ```

## Monitoring and Alerting

### Critical Alerts to Configure
```bash
# Control plane upgrade notifications
gcloud logging sinks create gke-upgrade-alerts \
  logging.googleapis.com/projects/PROJECT_ID/topics/gke-alerts \
  --log-filter='resource.type="gke_cluster" AND protoPayload.metadata.operationType:UPGRADE'

# Training job eviction alerts
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: eviction-monitor
data:
  query: |
    resource.type="gke_cluster" AND
    jsonPayload.reason="Evicted" AND
    jsonPayload.involvedObject.name:training
EOF
```

### Health Checks
```bash
# Weekly cluster health check (run during maintenance window)
#!/bin/bash
echo "=== Cluster Health Check ==="
kubectl get nodes -o wide
kubectl get pods -n kube-system | grep -v Running
kubectl get pdb -A | grep training
gcloud container clusters describe training-cluster --zone us-central1-a \
  --format="value(currentMasterVersion,nodePools[].version)"
```

## Security Considerations

While maximizing training protection, maintain security posture:

✅ **Maintained:** Control plane patches auto-applied (Extended channel timing)
✅ **Maintained:** Node security through Shielded GKE, Workload Identity
⚠️ **Delayed:** Node pool patches during exclusion periods
⚠️ **Manual:** Minor version upgrades require manual triggering

**Recommended security cadence:**
- Monthly control plane patches (automatic)
- Quarterly node pool updates (during training gaps)
- Bi-annual minor version upgrades (during major training campaign breaks)

## Cost Optimization

- **Extended channel cost:** Only charged during months 15-24 of version lifecycle
- **Dedicated training pool:** Taints prevent system workloads from consuming H100 nodes
- **Compact placement:** Ensures RDMA topology for multi-node training
- **System pool separation:** Regular nodes handle monitoring, logging, ingress

## Key Benefits of This Configuration

1. **Multi-week training protection** via persistent maintenance exclusions
2. **Security maintained** through automatic control plane patches
3. **Maximum upgrade control** with Extended channel + exclusions
4. **GPU-optimized settings** (maxUnavailable=1, no surge)
5. **Separation of concerns** (dedicated pools for training vs system workloads)
6. **Checkpoint-friendly termination** (1-hour graceful shutdown)
7. **Automatic exclusion renewal** (tracks version EoS without manual intervention)

This configuration provides the strongest protection for long-running training while maintaining a secure, manageable cluster lifecycle.