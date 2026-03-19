# GKE Upgrade Plan: Spot VM Node Pool Considerations

## Key Spot VM Considerations

**Spot VMs add complexity** to GKE upgrades because they can be preempted during the upgrade process, potentially causing cascading disruptions. Here's how to handle them safely:

## 1. Upgrade Strategy for Mixed Spot/On-Demand Pools

**Recommended approach: Conservative surge settings**
```bash
# Configure lower surge for spot pools to minimize disruption
gcloud container node-pools update SPOT_NODE_POOL \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0
```

**Why conservative?**
- Spot preemptions during upgrade can cause multiple simultaneous node losses
- Lower surge reduces the chance of losing both old and new nodes to preemption
- Gives workloads time to reschedule before next upgrade wave

## 2. Workload Protection Strategy

**Configure robust PDBs for spot-tolerant workloads:**
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: spot-workload-pdb
spec:
  minAvailable: 2  # Or 50% for larger deployments
  selector:
    matchLabels:
      app: your-app
```

**Ensure adequate replicas** — spot workloads should run with higher replica counts to handle simultaneous preemption + upgrade disruption:
- Minimum 3 replicas for critical services on spot
- Spread across zones with pod anti-affinity

## 3. Pre-Upgrade Checklist (Spot-Specific Items)

```
Spot VM Upgrade Readiness
- [ ] Spot workload replica counts adequate (≥3 for critical services)
- [ ] PDBs configured with minAvailable appropriate for spot volatility
- [ ] Anti-affinity rules spread workloads across zones/nodes
- [ ] Graceful shutdown handling (terminationGracePeriodSeconds ≥30s)
- [ ] Application retry logic handles rapid pod churn
- [ ] Non-spot node pools available for critical system workloads
- [ ] Recent spot preemption rates reviewed (Cloud Console → Compute Engine → Preemption history)
```

## 4. Alternative: Separate Node Pool Strategy

**Consider splitting mixed pools** before upgrading:

```bash
# Create dedicated spot pool
gcloud container node-pools create spot-pool-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --spot \
  --cluster-version 1.30 \
  --num-nodes 3 \
  --machine-type n2-standard-4

# Create dedicated on-demand pool  
gcloud container node-pools create ondemand-pool-v2 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.30 \
  --num-nodes 2 \
  --machine-type n2-standard-4
```

**Benefits:**
- Independent upgrade timing
- Tailored surge settings per pool type
- Clearer workload placement control

## 5. Upgrade Sequence

**Recommended order:**
1. **On-demand pools first** — provides stable capacity for critical workloads
2. **Spot pools second** — with conservative surge settings
3. **Monitor spot preemption rates** during upgrade window

## 6. Monitoring During Upgrade

```bash
# Watch for preemptions during upgrade
kubectl get events -A --field-selector reason=Preempted

# Monitor node stability
watch 'kubectl get nodes -l cloud.google.com/gke-preemptible=true'

# Check workload rescheduling
kubectl get pods -A --field-selector=status.phase=Pending
```

## 7. Troubleshooting Spot-Specific Issues

**Symptom:** Upgrade appears stuck with nodes constantly churning

**Diagnosis:**
```bash
# Check recent preemptions
kubectl get events -A --field-selector reason=Preempted --sort-by='.lastTimestamp'

# Verify spot vs upgrade node losses
kubectl describe nodes | grep "cloud.google.com/gke-preemptible"
```

**Fix:** Temporarily pause upgrade and wait for stable preemption period, or move critical workloads to on-demand nodes.

## 8. Post-Upgrade Validation

```bash
# Verify all spot nodes upgraded successfully
kubectl get nodes -l cloud.google.com/gke-preemptible=true \
  -o custom-columns=NAME:.metadata.name,VERSION:.status.nodeInfo.kubeletVersion

# Check workload distribution
kubectl get pods -A -o wide | grep spot-node-names
```

**Key insight:** Spot VM upgrades take longer due to the need for conservative settings, but this prevents the "double disruption" scenario where both preemption and upgrade hit simultaneously. Plan for 2-3x normal upgrade time for spot pools.

Would you like me to create a detailed runbook with the specific commands for your 1.29→1.30 upgrade, or focus on any particular aspect like workload migration strategies?