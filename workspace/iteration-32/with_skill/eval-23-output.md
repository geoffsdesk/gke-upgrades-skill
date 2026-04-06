# PDB Audit for GKE Upgrade Safety

Your concern is well-founded. Let me analyze each PDB configuration for upgrade safety:

## ⚠️ RISKY - Will Block Upgrades

**Service A: `minAvailable=100%`**
- **Problem**: Guarantees zero disruption tolerance — GKE cannot drain ANY pod
- **Impact**: Node upgrades will be completely blocked
- **Recommendation**: Change to `minAvailable=80%` or `maxUnavailable=1` to allow at least one pod to drain

**Service B: `maxUnavailable=0`**
- **Problem**: Identical to 100% availability requirement — no pods can be disrupted
- **Impact**: Will prevent any node from draining
- **Recommendation**: Change to `maxUnavailable=1` or `minAvailable=N-1` (where N = replica count)

## ✅ SAFE - Upgrade Compatible

**Service C: `minAvailable=2` with 3 replicas**
- **Analysis**: Allows 1 pod disruption (3-2=1), which is safe for rolling node upgrades
- **Verdict**: Well-configured — maintains service availability while allowing upgrades

**Service D: `maxUnavailable=1` with 5 replicas**
- **Analysis**: Allows 1 pod disruption while keeping 4 pods running
- **Verdict**: Excellent configuration — good availability with upgrade flexibility

## Recommended PDB Configurations

```yaml
# Service A - Fixed
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  maxUnavailable: 1  # Or minAvailable: 80%
  selector:
    matchLabels:
      app: service-a

# Service B - Fixed
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # Allows one pod to be disrupted
  selector:
    matchLabels:
      app: service-b
```

## General PDB Best Practices for GKE Upgrades

| Scenario | Recommended Setting | Reasoning |
|----------|-------------------|-----------|
| **2 replicas** | `maxUnavailable: 1` | Allows 1 pod drain, keeps 1 serving |
| **3+ replicas** | `maxUnavailable: 1` or `minAvailable: N-1` | Conservative but upgrade-safe |
| **Large scale (10+ replicas)** | `maxUnavailable: 25%` | Faster upgrades while maintaining availability |
| **Databases/StatefulSets** | `maxUnavailable: 1` | Protects quorum, one-at-a-time replacement |

## Pre-Upgrade PDB Validation Commands

```bash
# Check all PDBs and their disruption allowance
kubectl get pdb -A -o custom-columns=\
'NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN AVAILABLE:.spec.minAvailable,MAX UNAVAILABLE:.spec.maxUnavailable,ALLOWED DISRUPTIONS:.status.disruptionsAllowed'

# Find potentially problematic PDBs (zero disruptions allowed)
kubectl get pdb -A -o json | \
  jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name): \(.status.disruptionsAllowed) disruptions allowed"'

# Use GKE recommender to identify unpermissive PDBs
gcloud recommender insights list \
  --insight-type=google.container.DiagnosisInsight \
  --location=LOCATION \
  --project=PROJECT_ID \
  --filter="insightSubtype:PDB_UNPERMISSIVE"
```

## Immediate Action Required

**Before your next upgrade:**

1. **Fix Service A and B immediately** — they will block the upgrade entirely
2. **Test the changes** in a dev environment first
3. **Apply during your next maintenance window** — not during an active upgrade

```bash
# Emergency fix during a stuck upgrade (temporary)
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":null,"maxUnavailable":"1"}}'
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":"1"}}'

# Remember to update your source manifests permanently
```

## Monitoring During Upgrades

Set up monitoring for PDB violations during upgrades:

```bash
# Cloud Logging query for PDB-related upgrade blocks
resource.type="gke_cluster" 
jsonPayload.reason="EvictionBlocked"
jsonPayload.involvedObject.kind="Pod"
```

The **Services C and D are well-configured**, but **Services A and B will definitely block your upgrades** and need immediate fixing. This is one of the most common upgrade failure patterns we see.