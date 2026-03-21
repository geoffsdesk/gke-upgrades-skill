# GKE Configuration for H100 Foundation Model Training

## Executive Summary

For multi-week H100 training runs, your cluster needs **maximum upgrade control** while maintaining security. The key is using release channels with maintenance exclusions rather than avoiding auto-upgrades entirely.

## Recommended Cluster Configuration

### Release Channel Strategy
```bash
# Use Regular channel (not Extended) - best balance of stability and security patches
gcloud container clusters create foundation-training-cluster \
  --release-channel regular \
  --zone us-central1-a \
  --enable-autoupilot=false \
  --num-nodes 0
```

**Why Regular over Extended?** Extended channel requires manual minor version upgrades (no auto-upgrade for minors), adding operational overhead. Regular provides automatic security patches while giving you full control over disruptive upgrades via maintenance exclusions.

### Maintenance Control Setup

**1. Maintenance Windows (off-peak scheduling):**
```bash
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --maintenance-window-start "2024-12-15T06:00:00Z" \
  --maintenance-window-end "2024-12-15T10:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
```

**2. Persistent Maintenance Exclusions (maximum control):**
```bash
# "No minor or node upgrades" - allows CP security patches, blocks all disruptive changes
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-protection" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-until-end-of-support \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades
```

This exclusion **automatically tracks End of Support** and renews when new minor versions are adopted, so you don't need to manually chain exclusions.

### Node Pool Architecture

**Separate training and infrastructure pools:**

**Training Pool (H100s):**
```bash
gcloud container node-pools create h100-training \
  --cluster foundation-training-cluster \
  --zone us-central1-a \
  --machine-type a3-highgpu-8g \
  --num-nodes 0 \
  --enable-autoscaling \
  --min-nodes 0 \
  --max-nodes 64 \
  --node-locations us-central1-a \
  --accelerator type=nvidia-h100-80gb,count=8 \
  --enable-autorepair \
  --enable-autoupgrade=false \
  --max-surge-upgrade 0 \
  --max-unavailable-upgrade 1 \
  --reservation-affinity consume \
  --reservation RESERVATION_NAME \
  --enable-gvnic \
  --placement-type COMPACT
```

**System/Inference Pool (no GPUs):**
```bash
gcloud container node-pools create system-pool \
  --cluster foundation-training-cluster \
  --zone us-central1-a \
  --machine-type c2d-standard-8 \
  --num-nodes 2 \
  --enable-autoscaling \
  --min-nodes 2 \
  --max-nodes 10 \
  --enable-autorepair \
  --enable-autoupgrade \
  --max-surge-upgrade 2 \
  --max-unavailable-upgrade 0
```

**Key distinctions:**
- **H100 pool:** Auto-upgrade **disabled** at pool level, `maxUnavailable=1` (no surge capacity for H100s)
- **System pool:** Auto-upgrade **enabled**, can tolerate rolling updates
- **Compact placement:** Preserves RDMA topology for multi-node training

## GPU-Specific Upgrade Strategy

### During Active Training (Exclusion-Based Protection)
```bash
# Apply "no upgrades" exclusion during critical training runs (max 30 days)
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --add-maintenance-exclusion-name "training-run-dec2024" \
  --add-maintenance-exclusion-start-time "2024-12-15T00:00:00Z" \
  --add-maintenance-exclusion-end-time "2025-01-14T00:00:00Z" \
  --add-maintenance-exclusion-scope no_upgrades
```

This blocks **all upgrades** (including security patches) for up to 30 days. Use sparingly, only during active multi-week runs.

### Between Training Runs (Planned Upgrades)
```bash
# Upgrade H100 pool during planned maintenance windows
# 1. Cordon training nodes
kubectl cordon -l cloud.google.com/gke-nodepool=h100-training

# 2. Wait for current training jobs to complete and checkpoint
# (This is the key - wait for natural completion)

# 3. Upgrade the empty pool
gcloud container node-pools upgrade h100-training \
  --cluster foundation-training-cluster \
  --zone us-central1-a \
  --cluster-version TARGET_VERSION
```

### GPU Driver Compatibility
```bash
# Before upgrading, test in a separate staging cluster
gcloud container clusters create h100-staging \
  --release-channel regular \
  --cluster-version TARGET_VERSION \
  --zone us-central1-b

# Verify CUDA version matches your training framework requirements
# GKE auto-installs drivers - check compatibility matrix in staging first
```

## High-Performance Networking Configuration

For GPUDirect-TCPX and RDMA:
```bash
# Enable during cluster creation
gcloud container clusters create foundation-training-cluster \
  --network vpc-name \
  --subnetwork subnet-name \
  --enable-ip-alias \
  --enable-network-policy \
  --cluster-ipv4-cidr /21 \
  --services-ipv4-cidr /21 \
  --max-pods-per-node 32 \
  --enable-gvnic \
  --system-config-from-file system-config.yaml

# system-config.yaml should include:
# kubelet:
#   cpu_cfs_quota_period: "50ms"
#   cpu_cfs_quota: true
```

**Networking verification post-upgrade:**
```bash
# Test RDMA functionality after any upgrade
kubectl exec -it training-pod -- /opt/hpcx/tests/ib_write_bw
# Verify MTU settings preserved
kubectl exec -it training-pod -- ip link show
```

## Disruption Budget for Training Workloads

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: training-pdb
spec:
  minAvailable: "100%"  # Prevent any eviction during training
  selector:
    matchLabels:
      workload-type: foundation-training
```

**Important:** GKE respects PDBs for up to 1 hour during upgrades, then may force-drain. For multi-week jobs, the maintenance exclusion is your primary protection.

## Monitoring and Observability

**Upgrade notifications:**
```bash
# Enable 72-hour advance notifications (preview March 2026)
gcloud container clusters update foundation-training-cluster \
  --zone us-central1-a \
  --enable-upgrade-notifications
```

**Version monitoring:**
```bash
# Check auto-upgrade status and EoS timeline
gcloud container clusters get-upgrade-info foundation-training-cluster \
  --zone us-central1-a
```

## Security Considerations

**Control plane patches:** The "no minor or node upgrades" exclusion still allows control plane security patches. This maintains security posture while protecting training workloads.

**CVE response:** For critical CVEs requiring immediate node patches:
1. Checkpoint active training
2. Apply temporary "no upgrades" exclusion removal
3. Upgrade during maintenance window
4. Restore exclusions

## Operational Playbook

### Monthly Maintenance (Recommended Schedule)
1. **Week 1:** Plan upcoming training campaigns, review GKE release notes
2. **Week 2:** Stage upgrades in non-production environment
3. **Week 3:** Training completion window - upgrade production during natural gaps
4. **Week 4:** New training campaigns begin on updated infrastructure

### Emergency Procedures
```bash
# If upgrade gets stuck due to training workload blocking drain:
kubectl delete pdb training-pdb  # Temporarily remove protection
# Let upgrade complete, then restore PDB

# If forced to interrupt training:
kubectl exec training-pod -- /save_checkpoint.sh  # Custom checkpoint script
kubectl delete pod training-pod  # Allow upgrade to proceed
```

## Cost Optimization Notes

- **H100 reservation:** Essential for consistent availability and cost control
- **Mixed workloads:** Use separate non-GPU pools for inference/serving to avoid H100 waste
- **Autoscaling:** Scale training pools to zero between runs (H100s are expensive when idle)

This configuration gives you maximum control over disruptive upgrades while maintaining security through automatic control plane patching. The cluster will stay current on security fixes but won't interrupt your training runs with node-level changes unless you explicitly allow it.