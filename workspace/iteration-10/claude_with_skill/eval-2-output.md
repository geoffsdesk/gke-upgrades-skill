# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid channel) → 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (auto-upgrade scheduled next month)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot 1.31→1.32
- [ ] Dev clusters: ___ | Prod clusters: ___
- [ ] Current version: 1.31 | Target version: 1.32
- [ ] Auto-upgrade scheduled for: ___ (next month)

Compatibility & Breaking Changes
- [ ] 1.32 available in Stable channel verified (`gcloud container get-server-config --region REGION --format="yaml(channels)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard in Console)
- [ ] GKE 1.32 release notes reviewed for breaking changes from 1.31
- [ ] Third-party operators/controllers tested against 1.32 in dev clusters
- [ ] Admission webhooks validated against 1.32 API changes

Workload Readiness (Critical for Autopilot)
- [ ] All containers have resource requests specified (mandatory - pods will be rejected without them)
- [ ] PDBs configured for critical workloads (not overly restrictive - max 1h eviction timeout)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds ≤ 600s for graceful shutdown (Autopilot default)
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Database operators (if any) compatibility confirmed with K8s 1.32

Dev Environment Validation
- [ ] Dev clusters already on 1.32+ (Rapid channel should have it first)
- [ ] Application smoke tests passing on dev clusters with 1.32
- [ ] No regression in metrics, logs, or functionality observed in dev
- [ ] Load testing completed on dev environment with 1.32

Production Readiness
- [ ] Maintenance window configured for prod clusters (auto-upgrades respect windows)
- [ ] Consider maintenance exclusion if timing needs adjustment:
      - "No upgrades" (30-day max) - blocks everything for critical periods
      - "No minor or node upgrades" (until EoS) - allows CP patches only
- [ ] Scheduled upgrade notifications enabled (72h advance notice via Cloud Logging)
- [ ] Auto-upgrade target confirmed (`gcloud container clusters get-upgrade-info CLUSTER --region REGION`)

Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring)
- [ ] Baseline metrics captured (error rates, latency, throughput) for both prod clusters
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware and available during auto-upgrade window
- [ ] Rollback plan documented (control plane patches can be downgraded by customer)
```

## Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot 1.31→1.32

Cluster Health (Both Prod Clusters)
- [ ] Cluster 1 control plane at 1.32: `gcloud container clusters describe CLUSTER_1 --region REGION --format="value(currentMasterVersion)"`
- [ ] Cluster 2 control plane at 1.32: `gcloud container clusters describe CLUSTER_2 --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes auto-upgraded by Google (verify in Console - Autopilot handles node management)
- [ ] System pods healthy: `kubectl get pods -n kube-system` (both clusters)
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces` (both clusters)
- [ ] GKE managed components operational (ingress controllers, DNS, etc.)

Workload Health (Both Prod Clusters)
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/load balancers responding (test external endpoints)
- [ ] Application health checks and smoke tests passing
- [ ] Database connections and queries working (if applicable)

Resource & Autopilot-Specific Checks
- [ ] Pod resource requests still valid (no pods rejected for missing requests)
- [ ] Autopilot resource optimization working (check for right-sizing recommendations)
- [ ] No unexpected pod evictions or resource constraint issues
- [ ] Verify any Autopilot-managed node pools are healthy

Observability & Performance
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to Cloud Logging
- [ ] Error rates within pre-upgrade baseline (compare to dev cluster metrics)
- [ ] Latency (p50/p95/p99) within acceptable range
- [ ] APM/tracing working if configured

Cleanup & Documentation
- [ ] Verify dev clusters remain on latest Rapid channel version
- [ ] Update internal documentation with new cluster versions
- [ ] Lessons learned captured (any issues during auto-upgrade process)
- [ ] Consider if maintenance windows need adjustment for future upgrades
```

## Autopilot-Specific Notes

**Key differences from Standard clusters:**
- ✅ **No node pool management needed** - Google handles all node upgrades automatically
- ✅ **Simplified upgrade process** - Only control plane timing matters for planning
- ⚠️ **Resource requests mandatory** - Pods without requests will be rejected
- ⚠️ **Limited debugging options** - Use `kubectl debug` and Cloud Logging (no SSH access)

**Recommended approach for your setup:**
1. **Let dev clusters upgrade first** (Rapid channel) - they should already be on 1.32+
2. **Validate in dev** before prod auto-upgrades next month
3. **Use maintenance windows** to control when prod auto-upgrades happen
4. **Consider a brief maintenance exclusion** if you need to delay for a specific date

**Emergency controls if needed:**
```bash
# Apply 30-day "no upgrades" exclusion to delay auto-upgrade
gcloud container clusters update PROD_CLUSTER --region REGION \
  --add-maintenance-exclusion-name "delay-132-upgrade" \
  --add-maintenance-exclusion-start-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-end-time 2024-XX-XXTXX:XX:XXZ \
  --add-maintenance-exclusion-scope no_upgrades
```

Since you have the ideal dev→prod channel progression (Rapid→Stable), your dev clusters should validate 1.32 well before your prod auto-upgrade window!