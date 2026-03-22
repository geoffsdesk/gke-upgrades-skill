# PDB Configuration Audit for GKE Upgrades

I'll analyze each PDB configuration and explain the upgrade impact. PDBs are crucial for protecting workloads during upgrades, but overly restrictive settings can block node drains and stall upgrades.

## Configuration Analysis

### ❌ Service A: `minAvailable=100%` - **HIGH RISK**
**Problem:** This PDB will **block all upgrades**. GKE cannot drain any nodes because 100% of pods must remain available at all times.

**Impact:** Node drain will fail immediately. The upgrade will be stuck until you relax this PDB.

**Fix:**
```bash
# Temporarily allow 1 disruption during upgrades
kubectl patch pdb service-a-pdb -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":1}}'
```

### ❌ Service B: `maxUnavailable=0` - **HIGH RISK**
**Problem:** Identical to Service A - no disruptions allowed ever.

**Impact:** Same as Service A - will block all node drains.

**Fix:**
```bash
kubectl patch pdb service-b-pdb -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":1}}'
```

### ✅ Service C: `minAvailable=2` with 3 replicas - **SAFE**
**Analysis:** Allows 1 pod disruption (3 total - 2 required = 1 disruptable). This is ideal for rolling upgrades.

**Upgrade behavior:** GKE can drain 1 pod at a time, maintaining 2/3 service capacity throughout the upgrade.

### ✅ Service D: `maxUnavailable=1` with 5 replicas - **SAFE**
**Analysis:** Allows 1 pod disruption while keeping 4/5 pods running. Good balance of availability and upgrade flexibility.

**Upgrade behavior:** GKE can drain 1 pod at a time, maintaining 4/5 service capacity.

## Recommended PDB Strategy for Upgrades

### For most services (2+ replicas):
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: service-pdb
spec:
  selector:
    matchLabels:
      app: your-service
  maxUnavailable: 1  # Allow 1 pod disruption
```

### For high-replica services (10+ replicas):
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: large-service-pdb
spec:
  selector:
    matchLabels:
      app: your-service
  maxUnavailable: 25%  # Allow up to 25% disruption
```

### For single-replica services:
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: singleton-pdb
spec:
  selector:
    matchLabels:
      app: singleton-service
  maxUnavailable: 0  # Prevent disruption
```
**Note:** Single-replica PDBs with `maxUnavailable=0` will block upgrades. Consider if the service truly cannot tolerate brief downtime.

## Pre-Upgrade PDB Checklist

```bash
# 1. Audit all PDBs for blocking configurations
kubectl get pdb -A -o custom-columns="NAMESPACE:.metadata.namespace,NAME:.metadata.name,MIN-AVAILABLE:.spec.minAvailable,MAX-UNAVAILABLE:.spec.maxUnavailable,CURRENT-HEALTHY:.status.currentHealthy,DESIRED-HEALTHY:.status.desiredHealthy,DISRUPTIONS-ALLOWED:.status.disruptionsAllowed"

# 2. Identify risky PDBs (0 disruptions allowed)
kubectl get pdb -A -o json | jq -r '.items[] | select(.status.disruptionsAllowed == 0) | "\(.metadata.namespace)/\(.metadata.name)"'

# 3. Back up PDB configurations before modifying
kubectl get pdb -A -o yaml > pdb-backup-$(date +%Y%m%d).yaml
```

## Upgrade-Time PDB Management

### Temporary relaxation for blocked upgrades:
```bash
# Allow 1 disruption for Service A during upgrade
kubectl patch pdb service-a-pdb -n NAMESPACE \
  -p '{"spec":{"minAvailable":null,"maxUnavailable":1}}'

# Allow 1 disruption for Service B during upgrade  
kubectl patch pdb service-b-pdb -n NAMESPACE \
  -p '{"spec":{"maxUnavailable":1}}'

# Restore original configuration after upgrade
kubectl apply -f pdb-backup-$(date +%Y%m%d).yaml
```

### Monitor PDB status during upgrades:
```bash
# Watch PDB disruptions in real-time
watch 'kubectl get pdb -A -o wide'

# Check if PDBs are blocking node drain
kubectl get events -A --field-selector reason=EvictionBlocked
```

## Key Principles

1. **Never use `minAvailable=100%` or `maxUnavailable=0`** unless you have a single replica that truly cannot tolerate downtime
2. **Allow at least 1 disruption** for multi-replica services to enable rolling upgrades
3. **Use percentage values** for large deployments (e.g., `maxUnavailable: 25%`)
4. **Test PDB behavior** in staging clusters before applying to production
5. **Have a PDB relaxation playbook** ready for stuck upgrades

## GKE-Specific Behavior

- GKE respects PDBs for up to **1 hour** during node drains
- After 1 hour, GKE may force-drain nodes even with blocking PDBs
- Surge upgrades (`maxSurge > 0`) are more tolerant of restrictive PDBs because new capacity is added before old nodes are drained
- Blue-green upgrades completely avoid PDB conflicts by creating new nodes before draining old ones

Your Services C and D have ideal PDB configurations for upgrades. Services A and B need immediate attention to avoid blocking your next upgrade.