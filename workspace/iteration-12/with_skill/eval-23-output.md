# PDB Configuration Audit & Upgrade Risk Assessment

Here's your analysis with specific recommendations for each service:

## Risk Assessment Summary

| Service | Current PDB | Replicas | Risk Level | Upgrade Impact |
|---------|-------------|----------|------------|----------------|
| **Service A** | `minAvailable=100%` | Unknown | 🔴 **HIGH RISK** | **Will block upgrades** |
| **Service B** | `maxUnavailable=0` | Unknown | 🔴 **HIGH RISK** | **Will block upgrades** |
| **Service C** | `minAvailable=2` | 3 | 🟡 **MEDIUM RISK** | May block if surge insufficient |
| **Service D** | `maxUnavailable=1` | 5 | 🟢 **LOW RISK** | Should upgrade smoothly |

## Detailed Analysis

### 🔴 Service A: `minAvailable=100%` — BLOCKS UPGRADES
**Problem:** This PDB prevents ANY pod from being evicted, ever. During node upgrades, GKE needs to drain nodes, but this PDB will reject all eviction requests.

**Fix options:**
```bash
# Option 1: Allow 1 disruption (recommended)
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"75%","maxUnavailable":"25%"}}'

# Option 2: If you know replica count (e.g., 4 replicas)
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":3,"maxUnavailable":null}}'
```

### 🔴 Service B: `maxUnavailable=0` — BLOCKS UPGRADES
**Problem:** Identical to Service A — zero disruptions allowed means no pod can be evicted during node drain.

**Fix options:**
```bash
# Allow 1 disruption
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1,"minAvailable":null}}'

# Or percentage-based (if >4 replicas)
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":"25%","minAvailable":null}}'
```

### 🟡 Service C: `minAvailable=2` with 3 replicas — RISKY
**Analysis:** Only allows 1 pod disruption (3 replicas - 2 required = 1 disruption). This works IF:
- Your surge strategy can reschedule the evicted pod before draining the next node
- All 3 pods aren't on nodes being upgraded simultaneously

**Risk scenario:** If 2+ pods land on the same upgrade batch, the PDB blocks eviction.

**Recommendations:**
```bash
# Option 1: Keep current (acceptable risk for most workloads)
# No change needed - monitor during upgrade

# Option 2: Be more permissive (if service can handle it)
kubectl patch pdb service-c-pdb -p '{"spec":{"minAvailable":1,"maxUnavailable":null}}'
```

### 🟢 Service D: `maxUnavailable=1` with 5 replicas — SAFE
**Analysis:** Perfect configuration. Allows 1 disruption while keeping 4/5 pods running. This gives GKE enough flexibility to drain nodes while maintaining service availability.

**Action:** No changes needed. This is the gold standard.

## Upgrade-Safe PDB Guidelines

### ✅ Safe patterns:
- `maxUnavailable=1` with 3+ replicas
- `maxUnavailable="25%"` with 4+ replicas  
- `minAvailable` that leaves at least 1 disruption allowed
- Higher disruption tolerance for batch/background workloads

### ❌ Dangerous patterns:
- `minAvailable=100%` or `maxUnavailable=0` (blocks ALL evictions)
- `minAvailable` equals replica count
- PDBs on single-replica deployments
- PDBs that don't account for node anti-affinity spreading

## Pre-Upgrade PDB Audit Commands

```bash
# Quick audit - find blocking PDBs
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,ALLOWED-DISRUPTIONS:.status.disruptionsAllowed"

# Identify zero-disruption PDBs (upgrade blockers)
kubectl get pdb -A -o json | jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name) - BLOCKS UPGRADES"'

# Check replica counts vs PDB settings
kubectl get deployments -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,REPLICAS:.spec.replicas"
```

## Recommended Fixes Before Upgrade

### Immediate fixes (apply now):
```bash
# Fix Service A - allow 25% disruption
kubectl patch pdb service-a-pdb -p '{"spec":{"minAvailable":"75%","maxUnavailable":null}}'

# Fix Service B - allow 1 disruption  
kubectl patch pdb service-b-pdb -p '{"spec":{"maxUnavailable":1,"minAvailable":null}}'
```

### During upgrade monitoring:
```bash
# Watch for PDB violations during upgrade
kubectl get events -A --field-selector reason=EvictionBlocked -w

# Monitor upgrade progress
watch 'kubectl get nodes -L cloud.google.com/gke-nodepool'
```

### Temporary relaxation strategy (if needed):
If upgrades still get stuck, temporarily relax PDBs during the upgrade window:

```bash
# Back up current PDBs
kubectl get pdb -A -o yaml > pdb-backup.yaml

# Temporarily allow more disruptions
kubectl patch pdb service-c-pdb -p '{"spec":{"minAvailable":1}}'

# Restore after upgrade
kubectl apply -f pdb-backup.yaml
```

## Key Takeaway

**Services A and B will definitely block your upgrades** and need immediate fixes. Service C is borderline risky depending on your node upgrade strategy. Service D is perfectly configured.

The golden rule: **Always allow at least 1 disruption per PDB**, and ensure your total allowed disruptions across all PDBs don't exceed your surge upgrade parallelism.