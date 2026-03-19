# GKE Control Plane Upgrade

Manages the upgrade of GKE Control Planes with a focus on API stability and zero-downtime for regional clusters.

## Pre-Upgrade Checks

Before recommending any control plane upgrade:

1. **API Deprecation Scan**: Check for active use of deprecated Kubernetes APIs that will be removed in the target version. Use `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated` or the GKE deprecation insights dashboard.

2. **Regional vs Zonal Impact**:
   - **Regional clusters**: Control plane upgrade is zero-downtime (rolling update across 3 replicas)
   - **Zonal clusters**: Control plane is unavailable for 5-15 minutes during upgrade. Warn the user explicitly.

3. **Release Channel Verification**: Confirm the target version is available in the cluster's current release channel. Use `gcloud container get-server-config --zone ZONE --format="yaml(channels)"`.

4. **Version Path**: Control planes cannot skip minor versions. For multi-version jumps (e.g., 1.28 → 1.30), plan sequential upgrades with validation between each step.

## Upgrade Execution

```bash
# Check current version
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version TARGET_VERSION

# Verify (wait ~10-15 min for regional, ~5 min for zonal)
gcloud container clusters describe CLUSTER_NAME \
  --zone ZONE \
  --format="value(currentMasterVersion)"

# Validate system pods
kubectl get pods -n kube-system
```

## Post-Upgrade Validation

- Verify API server is responding: `kubectl cluster-info`
- Check system pods healthy: `kubectl get pods -n kube-system`
- Confirm no degraded webhooks: `kubectl get validatingwebhookconfigurations`
- Verify node communication: `kubectl get nodes` (all should show Ready)

## Autopilot Considerations

For Autopilot clusters, the control plane upgrade is the primary upgrade event since Google manages nodes. Focus on:
- Timing via maintenance windows
- Workload readiness (resource requests, PDBs)
- Testing on dev clusters (Rapid channel) before prod auto-upgrades hit
