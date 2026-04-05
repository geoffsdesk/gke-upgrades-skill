# PDB Configuration Audit for GKE Upgrades

## Current Configuration Analysis

| Service | PDB Setting | Replicas | Risk Level | Upgrade Impact |
|---------|-------------|----------|------------|----------------|
| **Service A** | `minAvailable: 100%` | Unknown | 🔴 **HIGH RISK** | **Will block upgrades** - No pods can be evicted |
| **Service B** | `maxUnavailable: 0` | Unknown | 🔴 **HIGH RISK** | **Will block upgrades** - No pods can be evicted |
| **Service C** | `minAvailable: 2` (3 replicas) | 3 | 🟡 **MEDIUM RISK** | **May block if multi-zone** - Only 1 pod can be evicted |
| **Service D** | `maxUnavailable: 1` (5 replicas) | 5 | 🟢 **LOW RISK** | **Upgrade-safe** - Allows 1 pod eviction, 4 remain |

## Detailed Risk Assessment

### 🔴 Service A & B: Upgrade Blockers (CRITICAL)
**Problem:** `minAvailable: 100%` and `maxUnavailable: 0` are equivalent — both prevent ANY pod eviction.

**Upgrade Impact:**
- During node drain, GKE cannot evict pods from nodes being upgraded
- Upgrade will stall until you manually relax the PDB
- After 1 hour, GKE may force-evict pods anyway, defeating the PDB's purpose

**Recommended Fix:**
```yaml
# Service A - Allow 1 pod disruption
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-a-pdb
spec:
  minAvailable: 2  # or use maxUnavailable: 1
  selector:
    matchLabels:
      app: service-a

# Service B - Allow 1 pod disruption  
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-b-pdb
spec:
  maxUnavailable: 1  # allows orderly drain
  selector:
    matchLabels:
      app: service-b
```

### 🟡 Service C: Zone-Dependent Risk
**Current:** `minAvailable: 2` with 3 replicas = only 1 pod can be evicted

**Risk Analysis:**
- **Single-zone cluster:** Low risk — 1 node drains at a time, 1 pod eviction is sufficient
- **Multi-zone cluster:** Medium risk — if 2+ pods are on the same zone being upgraded, upgrade blocks

**Check your pod distribution:**
```bash
kubectl get pods -l app=service-c -o wide
# Look at the NODE column - are pods spread across zones?
```

**Recommended Actions:**
1. **Add pod anti-affinity** to spread pods across zones:
```yaml
spec:
  template:
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchLabels:
                  app: service-c
              topologyKey: topology.kubernetes.io/zone
```

2. **Consider scaling to 4+ replicas** if traffic justifies it — gives more eviction headroom

### 🟢 Service D: Upgrade-Safe Configuration ✅
**Current:** `maxUnavailable: 1` with 5 replicas

**Why it works:**
- Allows 1 pod eviction per drain cycle
- Maintains 4 healthy replicas during upgrade
- Compatible with both single-zone and multi-zone clusters
- Provides good balance of availability and upgrade flexibility

## GKE Upgrade Behavior with PDBs

### How GKE Respects PDBs During Upgrades
1. **Surge upgrade process:** Create new node → cordon old node → drain old node → delete old node
2. **During drain:** GKE respects PDB constraints for up to **1 hour**
3. **After 1 hour:** GKE force-evicts remaining pods, bypassing PDB protection
4. **Monitoring:** GKE sends disruption event notifications when PDBs block eviction

### PDB Timeout Notifications
Monitor for PDB violations during upgrades:
```bash
# Check for PDB-related events
kubectl get events -A --field-selector reason=EvictionBlocked

# Cloud Logging query for disruption events
resource.type="gke_cluster" 
jsonPayload.reason="POD_PDB_VIOLATION"
```

## Upgrade-Safe PDB Recommendations

### General Guidelines
- **Always allow at least 1 pod disruption** — `maxUnavailable: 1` or `minAvailable: N-1`
- **Use percentage-based PDBs for large deployments:** `maxUnavailable: 25%` scales with replica count
- **Avoid `100%` availability requirements** — they're incompatible with rolling upgrades
- **Test PDB settings** in dev/staging environments during upgrade rehearsals

### Service-Type Recommendations

**Web services/APIs (stateless):**
```yaml
spec:
  maxUnavailable: 25%  # Scales with deployment size
  # or minAvailable: 75% for large deployments
```

**Databases (stateful):**
```yaml
spec:
  maxUnavailable: 1  # Conservative, preserves quorum
  # For 3-node databases, allows 1 disruption while keeping 2 healthy
```

**Message queues/caches:**
```yaml
spec:
  minAvailable: 2  # Maintains cluster quorum
  # Adjust based on your clustering requirements
```

## Pre-Upgrade PDB Checklist

```markdown
Pre-Upgrade PDB Validation
- [ ] No PDBs with `minAvailable: 100%` or `maxUnavailable: 0`
- [ ] All PDBs allow at least 1 pod disruption
- [ ] Multi-replica services have pod anti-affinity configured
- [ ] PDB selectors match actual pod labels
- [ ] Disruption event monitoring configured (Cloud Logging/Pub/Sub)
- [ ] Emergency PDB relaxation procedure documented
```

## Emergency PDB Relaxation Procedure

If upgrades get blocked despite following these recommendations:

```bash
# 1. Identify blocking PDB
kubectl get pdb -A -o wide
# Look for ALLOWED DISRUPTIONS = 0

# 2. Temporarily relax the PDB
kubectl patch pdb SERVICE_PDB_NAME -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":"50%"}}'

# 3. Monitor upgrade progress
watch 'kubectl get nodes -o wide'

# 4. Restore original PDB after upgrade
kubectl get pdb SERVICE_PDB_NAME -n NAMESPACE -o yaml > original-pdb.yaml
kubectl apply -f original-pdb.yaml
```

## Summary & Action Items

**Immediate Actions Required:**
1. **Fix Service A & B** — change to `maxUnavailable: 1` or `minAvailable: N-1`
2. **Verify Service C pod distribution** across zones
3. **Test all PDB changes** in a dev cluster upgrade first

**Service D is already upgrade-safe** — no changes needed.

Would you like me to help you create the updated PDB configurations, or do you need guidance on testing these changes in your development environment first?