# GKE Autopilot Upgrade Checklists
**Environment:** 2 prod clusters | Autopilot | Stable channel | 1.29 → 1.30

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Production Autopilot Clusters
- [ ] Cluster 1: ___ | Cluster 2: ___ | Mode: Autopilot | Channel: Stable
- [ ] Current version: 1.29.x | Target version: 1.30.x

Compatibility
- [ ] K8s 1.30 available in Stable channel (check notifications/console)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.29 → 1.30 breaking changes
- [ ] Third-party operators/controllers compatible with K8s 1.30
- [ ] Admission webhooks tested against K8s 1.30 (if any)

Workload Readiness (Autopilot Requirements)
- [ ] ALL containers have resource requests (CPU/memory) - mandatory in Autopilot
- [ ] No bare pods — all managed by Deployments/StatefulSets/Jobs
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] terminationGracePeriodSeconds ≤ 600s (Autopilot limit)
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] No privileged containers or host network usage (unsupported in Autopilot)

Testing Pipeline
- [ ] Rapid channel dev clusters already upgraded to 1.30 and validated
- [ ] Application smoke tests passing on dev 1.30 clusters
- [ ] Load testing completed on dev environment post-upgrade

Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring)
- [ ] Baseline metrics captured (error rates, latency, throughput)
- [ ] Auto-upgrade timing confirmed (check cluster maintenance window)
- [ ] Stakeholders notified of upgrade window
- [ ] On-call team aware (limited rollback options in Autopilot)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Production Autopilot Clusters

Cluster Health
- [ ] Cluster 1 control plane at 1.30.x: `gcloud container clusters describe CLUSTER1 --region REGION --format="value(currentMasterVersion)"`
- [ ] Cluster 2 control plane at 1.30.x: `gcloud container clusters describe CLUSTER2 --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes auto-upgraded (Autopilot manages this): `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces`

Workload Health (Both Clusters)
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] No resource request violations causing pod rejection
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress controllers and load balancers responding
- [ ] Application health checks and smoke tests passing

Observability
- [ ] Metrics pipeline active, no collection gaps
- [ ] Cloud Logging flowing normally
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] No increase in resource throttling events

Cleanup & Documentation
- [ ] Autopilot auto-cleanup verified (no manual intervention needed)
- [ ] Upgrade documented in changelog
- [ ] Dev clusters ready for next Rapid channel version
- [ ] Lessons learned captured for next upgrade cycle
```

## Autopilot-Specific Notes

**Key differences from Standard clusters:**
- Node upgrades happen automatically after control plane (you can't control timing)
- No surge settings or blue-green strategies available
- Resource requests are mandatory — missing requests = pod rejection
- Limited troubleshooting (no SSH, use `kubectl debug` and Cloud Logging)

**Validation commands for Autopilot:**
```bash
# Check for resource request violations
kubectl get events -A --field-selector reason=FailedCreate | grep -i "resource"

# Verify no privileged workloads (will be rejected)
kubectl get pods -A -o jsonpath='{.items[*].spec.securityContext.privileged}' | grep -v false

# Check Autopilot-managed node pools
gcloud container node-pools list --cluster CLUSTER --region REGION
```

Since your dev clusters are on Rapid channel, use them as your testing ground — they'll get 1.30 first, giving you validation time before prod auto-upgrades on Stable.