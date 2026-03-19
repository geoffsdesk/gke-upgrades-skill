# GKE API Deprecations Reference

## How to Check for Deprecated API Usage

```bash
# Check cluster metrics for deprecated API calls
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated

# Use GKE deprecation insights (Console)
# Navigation: GKE > Cluster > Upgrade Insights > Deprecation Insights

# Check specific API groups
kubectl api-resources | grep -i beta
```

## Common Deprecation Patterns by Version

### 1.25
- PodSecurityPolicy removed (use Pod Security Standards instead)
- `policy/v1beta1` PodDisruptionBudget → `policy/v1`

### 1.26
- `flowcontrol.apiserver.k8s.io/v1beta1` → `flowcontrol.apiserver.k8s.io/v1beta3`
- `autoscaling/v2beta1` HPA → `autoscaling/v2`

### 1.27
- `storage.k8s.io/v1beta1` CSIStorageCapacity removed
- `CSIMigration*` feature gates removed (CSI migration is permanent)

### 1.29
- `flowcontrol.apiserver.k8s.io/v1beta2` removed → `v1beta3` or `v1`

### 1.32
- `flowcontrol.apiserver.k8s.io/v1beta3` removed → `v1`

## Impact of Deprecated APIs on Upgrades

- GKE checks for deprecated API usage before auto-upgrades
- If deprecated APIs are detected, GKE may delay the auto-upgrade and notify via Pub/Sub
- For EOL versions, GKE will force upgrade even with deprecated API usage (with 30-day advance notice)
- Manual upgrades are not blocked by deprecated API usage (proceed at your own risk)

## Remediation Workflow

1. Identify deprecated API usage via metrics or insights dashboard
2. Update client code / manifests to use the replacement API
3. Verify no deprecated API calls remain in metrics
4. Proceed with upgrade

```bash
# Example: migrate PDB from v1beta1 to v1
kubectl get pdb -A -o yaml | sed 's/policy\/v1beta1/policy\/v1/' | kubectl apply -f -
```
