# Pre-Upgrade Checklist - Autopilot Production Clusters

```
Pre-Upgrade Checklist
- [ ] Cluster: [PROD-CLUSTER-1] | Mode: Autopilot | Channel: Stable
- [ ] Cluster: [PROD-CLUSTER-2] | Mode: Autopilot | Channel: Stable  
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility
- [ ] 1.32 confirmed available in Stable channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard in Console)
- [ ] GKE 1.32 release notes reviewed for breaking changes from 1.31
- [ ] Third-party operators/controllers tested against 1.32 (use dev clusters for validation)
- [ ] Admission webhooks tested against 1.32 control plane

Workload Readiness (Autopilot-specific)
- [ ] All containers have resource requests defined (mandatory - missing requests cause pod rejection)
- [ ] All containers have resource limits defined (recommended for predictable scheduling)
- [ ] PDBs configured for critical workloads (not overly restrictive - allow some disruption)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds ≤ 300s for faster pod turnover during upgrades
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Database operators (if any) compatible with K8s 1.32

Dev Validation (leverage your Rapid clusters)
- [ ] Dev clusters (Rapid channel) already running 1.32+ - validate application behavior
- [ ] Integration tests passed on dev clusters with 1.32
- [ ] No performance regressions observed in dev after 1.32 upgrade
- [ ] Custom metrics/monitoring working correctly on 1.32 in dev

Auto-Upgrade Controls
- [ ] Auto-upgrade target confirmed: `gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion,releaseChannel)"`
- [ ] Maintenance window configured for off-peak hours:
      ```bash
      gcloud container clusters update CLUSTER --zone ZONE \
        --maintenance-window-start 2024-XX-XXTXX:XX:XXZ \
        --maintenance-window-end 2024-XX-XXTXX:XX:XXZ \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SU"
      ```
- [ ] Consider "no minor upgrades" exclusion if you need to delay (up to 1.31 EoS):
      ```bash
      gcloud container clusters update CLUSTER --zone ZONE \
        --add-maintenance-exclusion-name "delay-1-32" \
        --add-maintenance-exclusion-start-time START_TIME \
        --add-maintenance-exclusion-end-time END_TIME \
        --add-maintenance-exclusion-scope no_minor_upgrades
      ```
- [ ] Scheduled upgrade notifications enabled (72h advance notice via Cloud Logging)

Multi-Cluster Coordination  
- [ ] Upgrade sequence planned: Prod cluster 1 → soak time → Prod cluster 2
- [ ] Sufficient soak time planned between prod clusters (recommend 24-48h minimum)
- [ ] Load balancing/traffic routing plan if one cluster needs to handle full load
- [ ] Cross-cluster dependencies identified (shared databases, message queues, etc.)

Ops Readiness
- [ ] Monitoring dashboards active (workload health, error rates, latency)
- [ ] Baseline metrics captured before upgrade
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware and available during maintenance window
- [ ] Rollback plan documented (primarily workload-level - Autopilot handles infrastructure)
```

# Post-Upgrade Checklist - Autopilot Production Clusters

```
Post-Upgrade Checklist

Control Plane Health (Autopilot manages nodes automatically)
- [ ] Cluster 1 control plane at 1.32: `gcloud container clusters describe CLUSTER-1 --zone ZONE --format="value(currentMasterVersion)"`
- [ ] Cluster 2 control plane at 1.32: `gcloud container clusters describe CLUSTER-2 --zone ZONE --format="value(currentMasterVersion)"`
- [ ] System pods healthy: `kubectl get pods -n kube-system` (both clusters)
- [ ] GKE-managed nodes automatically upgraded (Autopilot handles this)
- [ ] All nodes Ready: `kubectl get nodes` (both clusters)

Workload Health  
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Jobs completing successfully: `kubectl get jobs -A`
- [ ] Ingress controllers responding (test external endpoints)
- [ ] Application health checks and smoke tests passing

Resource Allocation (Autopilot-specific)
- [ ] No pods rejected for missing resource requests
- [ ] Autopilot resource allocation working correctly (check pod specs for injected requests/limits)
- [ ] Custom resource classes working if used
- [ ] No unexpected resource scaling behavior

Cross-Cluster Validation
- [ ] Both prod clusters healthy before proceeding with any traffic shifts
- [ ] Load balancing between clusters working correctly  
- [ ] Cross-cluster communication healthy (if applicable)
- [ ] Shared services (databases, queues) accessible from both upgraded clusters

Observability & Performance
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to Cloud Logging without errors
- [ ] Error rates within pre-upgrade baseline (compare to dev cluster metrics)
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] Custom metrics and dashboards working correctly
- [ ] No new error patterns in Cloud Logging

Final Steps
- [ ] Remove any temporary maintenance exclusions if applied
- [ ] Update internal documentation with new cluster versions
- [ ] Lessons learned documented for next upgrade cycle
- [ ] Dev teams notified that prod is now on 1.32 (matches dev environment post-upgrade)
```

## Key Autopilot Notes:

1. **No node pool management needed** - Google handles all node upgrades automatically after the control plane
2. **Resource requests are mandatory** - missing requests will cause pod rejection in Autopilot
3. **Use your Rapid dev clusters for early validation** - they'll get 1.32 first, giving you real-world testing
4. **Sequence your prod upgrades** - don't upgrade both simultaneously, use soak time between them
5. **Maintenance windows control timing** - auto-upgrades respect these, giving you predictable scheduling

Would you like me to generate the specific gcloud commands for setting up maintenance windows for your clusters, or help you plan the upgrade sequence timing?