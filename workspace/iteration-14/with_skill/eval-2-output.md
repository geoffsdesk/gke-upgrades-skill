# GKE Autopilot 1.31→1.32 Upgrade Checklists

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist
- [ ] Clusters: 2 Autopilot prod clusters | Channel: Stable
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility & Version Strategy
- [ ] Dev clusters (Rapid) already on 1.32 - validate compatibility there first
- [ ] Target version 1.32 available in Stable channel (`gcloud container get-server-config --region REGION --format="yaml(channels.STABLE)"`)
- [ ] GKE 1.32 release notes reviewed for breaking changes from 1.31→1.32
- [ ] No deprecated API usage detected:
      - Check GKE deprecation insights in Console → Kubernetes Engine → Recommendations
      - CLI check: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Third-party operators/controllers tested on dev (Rapid) clusters and confirmed compatible
- [ ] Admission webhooks (cert-manager, policy controllers) verified working on 1.32 dev clusters

Workload Readiness (Autopilot-specific)
- [ ] All containers have CPU/memory resource requests (mandatory in Autopilot)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs
- [ ] PDBs configured for critical workloads (not overly restrictive - allow some disruption)
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown (default 30s usually sufficient)
- [ ] StatefulSet data backed up if applicable, PV reclaim policies verified
- [ ] Horizontal Pod Autoscaler (HPA) configurations reviewed - no breaking changes in 1.32

Auto-Upgrade Control (since you're getting notifications)
- [ ] Maintenance windows configured for off-peak hours if desired:
      ```
      gcloud container clusters update CLUSTER_NAME \
        --region REGION \
        --maintenance-window-start YYYY-MM-DDTHH:MM:SSZ \
        --maintenance-window-end YYYY-MM-DDTHH:MM:SSZ \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
      ```
- [ ] Consider adding "no minor upgrades" exclusion to delay if needed:
      ```
      gcloud container clusters update CLUSTER_NAME \
        --region REGION \
        --add-maintenance-exclusion-name "delay-1-32" \
        --add-maintenance-exclusion-start-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
        --add-maintenance-exclusion-end-time YYYY-MM-DDTHH:MM:SSZ \
        --add-maintenance-exclusion-scope no_minor_upgrades
      ```

Environment Strategy
- [ ] Dev clusters (Rapid) serving as canaries - monitor their health on 1.32
- [ ] Coordinate upgrade timing between both prod clusters if needed
- [ ] Rollout sequencing considered if clusters are interdependent

Ops Readiness
- [ ] Monitoring and alerting active (Cloud Monitoring)
- [ ] Baseline metrics captured from dev clusters on 1.32
- [ ] Upgrade timeline communicated to stakeholders
- [ ] On-call team aware of auto-upgrade schedule
- [ ] 72h scheduled upgrade notifications enabled (Preview):
      ```
      gcloud logging sinks list --format="value(name)" | grep upgrade-notifications
      ```
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist

Cluster Health
- [ ] Cluster 1 control plane at 1.32.x: `gcloud container clusters describe CLUSTER_1 --region REGION --format="value(currentMasterVersion)"`
- [ ] Cluster 2 control plane at 1.32.x: `gcloud container clusters describe CLUSTER_2 --region REGION --format="value(currentMasterVersion)"`
- [ ] All system pods healthy: `kubectl get pods -n kube-system` (both clusters)
- [ ] Autopilot node pools auto-upgraded by Google (no manual action needed)
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces` (both clusters)
- [ ] GKE-managed components operational (cluster autoscaler, VPA, etc.)

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A` (both clusters)
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A` (both clusters)
- [ ] HPA scaling working correctly: `kubectl get hpa -A` (both clusters)
- [ ] Ingress controllers and load balancers responding
- [ ] Application health checks and smoke tests passing
- [ ] Cross-cluster communication working if applicable

Autopilot-Specific Validation
- [ ] Resource requests still compliant (Autopilot enforces this)
- [ ] No resource limit violations after upgrade
- [ ] Workload Identity still functional if used
- [ ] Binary Authorization policies still enforcing if configured
- [ ] VPC-native networking and Private Google Access working

Observability
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to Cloud Logging
- [ ] Error rates within pre-upgrade baseline (compare to dev clusters)
- [ ] Latency (p50/p95/p99) within expected ranges
- [ ] Custom metrics and dashboards showing expected values

Cleanup & Documentation
- [ ] Remove temporary maintenance exclusions if any were added
- [ ] Update infrastructure documentation with new version
- [ ] Lessons learned from dev→prod upgrade cycle captured
- [ ] Monitor dev clusters (Rapid) for next minor version behavior
```

## Key Notes for Your Setup

**Leverage your dev clusters:** Since your dev clusters on Rapid channel are already running 1.32, use them to validate compatibility before your prod auto-upgrades. Any issues you discover can be fixed before they impact production.

**Auto-upgrade timing:** The notifications give you advance notice, but Stable channel upgrades are automatic. If you need to delay, apply a maintenance exclusion. Otherwise, just ensure your maintenance windows are set appropriately.

**Autopilot simplicity:** Node pool management is handled by Google, so your main concerns are workload compatibility and control plane timing. The upgrade process is much simpler than Standard clusters.

**Multi-cluster coordination:** If your two prod clusters are interdependent, consider staggering their maintenance windows by a few hours to avoid simultaneous upgrades.