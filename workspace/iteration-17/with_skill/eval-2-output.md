# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid channel) + 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (minor version)  
**Timeline:** Auto-upgrade next month

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Dev clusters: ___ | Prod clusters: ___

Compatibility & Validation
- [ ] Dev clusters already at 1.32+ (validate in dev first): `gcloud container clusters describe DEV_CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] No deprecated API usage in dev/prod: Check GKE deprecation insights dashboard or `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] GKE 1.32 release notes reviewed for Autopilot-specific changes
- [ ] Third-party operators/controllers tested in dev and compatible with 1.32
- [ ] Admission webhooks (cert-manager, policy controllers) verified in dev

Workload Readiness (All containers MUST have resource requests in Autopilot)
- [ ] All containers have CPU/memory requests: `kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[] | .resources.requests == null or .resources.requests.cpu == null or .resources.requests.memory == null) | {ns:.metadata.namespace, name:.metadata.name}'`
- [ ] PDBs configured for critical workloads (not overly restrictive - Autopilot respects PDBs for max 1 hour)
- [ ] No bare pods — all managed by controllers
- [ ] terminationGracePeriodSeconds ≤ 600s (10 min max for Autopilot, 25s for Spot)
- [ ] StatefulSet data backed up, PV reclaim policies verified
- [ ] HPA/VPA configurations tested in dev with 1.32

Operations & Timing
- [ ] Maintenance windows configured for prod clusters (Autopilot respects windows for control plane upgrades):
      ```
      gcloud container clusters update PROD_CLUSTER --region REGION \
        --maintenance-window-start "YYYY-MM-DDTHH:MM:SSZ" \
        --maintenance-window-duration 4h \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
      ```
- [ ] Consider "no minor upgrades" maintenance exclusion if you need to delay:
      ```
      gcloud container clusters update PROD_CLUSTER --region REGION \
        --add-maintenance-exclusion-scope no_minor_upgrades \
        --add-maintenance-exclusion-until-end-of-support
      ```
- [ ] Baseline metrics captured (error rates, latency, throughput) in both dev and prod
- [ ] On-call team aware of upgrade timeline
- [ ] Stakeholders notified of maintenance window

Dev Validation Complete
- [ ] Dev clusters running 1.32+ for at least 1 week with no issues
- [ ] Critical user journeys tested in dev
- [ ] All application health checks passing in dev
- [ ] No regression in dev cluster performance/stability
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Cluster Health (Both prod clusters)
- [ ] Control plane at 1.32+: `gcloud container clusters describe PROD_CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes at 1.32+ (Autopilot manages this): `kubectl get nodes -o wide`
- [ ] All nodes Ready: `kubectl get nodes | grep -v Ready`
- [ ] System pods healthy: `kubectl get pods -n kube-system | grep -v Running`

Workload Health (Both prod clusters)
- [ ] All deployments at desired replica count: `kubectl get deployments -A | grep -v "READY.*READY"`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded | grep -v "No resources found"`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A | grep -v "READY.*READY"`
- [ ] HPA/VPA functioning correctly: `kubectl get hpa -A` and `kubectl get vpa -A`
- [ ] Ingress/load balancers responding (test external endpoints)

Application Validation
- [ ] Critical user journeys working (run smoke tests)
- [ ] Application health checks and readiness probes passing
- [ ] Database connections stable (if applicable)
- [ ] External integrations functioning

Observability & Performance
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to Cloud Logging
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] Resource utilization normal (CPU/memory requests being honored)

Cleanup & Documentation
- [ ] No failed pods or stuck resources requiring cleanup
- [ ] Upgrade documented in changelog/runbook
- [ ] Remove temporary maintenance exclusions if applied
- [ ] Schedule next upgrade window for future minor versions
- [ ] Lessons learned captured (especially any Autopilot-specific issues)
```

## Key Autopilot Considerations

**Resource requests are mandatory:** Any container without CPU/memory requests will be rejected. This is the #1 cause of post-upgrade pod failures in Autopilot.

**Simplified upgrade process:** You only control control plane timing via maintenance windows and exclusions. Google manages all node operations automatically using surge upgrades (~20 nodes in parallel).

**Termination limits:** Autopilot enforces stricter termination grace periods (10 min standard, 25s for Spot) compared to Standard clusters.

**Validation strategy:** Since your dev clusters are on Rapid channel, they'll upgrade to 1.32 before your prod clusters. Use this natural staging to validate workload compatibility before the prod upgrade.

**Maintenance exclusion recommendation:** If you need more control over the upgrade timing, use `--add-maintenance-exclusion-scope no_minor_upgrades --add-maintenance-exclusion-until-end-of-support` on your prod clusters. This blocks auto-minor upgrades while still allowing security patches, giving you control over when to manually trigger the 1.31→1.32 upgrade.