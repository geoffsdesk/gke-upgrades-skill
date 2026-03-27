# GKE Autopilot 1.31→1.32 Upgrade Checklists

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot Production 1.31→1.32
- [ ] Clusters: [PROD-CLUSTER-1] [PROD-CLUSTER-2] | Mode: Autopilot | Channel: Stable
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility & Breaking Changes
- [ ] 1.32 available in Stable channel confirmed (`gcloud container get-server-config --region REGION --format="yaml(channels.stable)"`)
- [ ] No deprecated API usage (check GKE deprecation insights in console)
- [ ] GKE 1.32 release notes reviewed for breaking changes from 1.31
- [ ] Third-party operators/controllers compatible with 1.32 verified
- [ ] Admission webhooks (cert-manager, policy controllers) tested against 1.32

Dev Environment Validation (Leverage Rapid clusters)
- [ ] Dev clusters (Rapid channel) already at 1.32 and stable for 2+ weeks
- [ ] All critical workloads deployed and tested on dev 1.32 clusters
- [ ] Performance baselines captured on dev - no regressions observed
- [ ] CI/CD pipelines validated against 1.32 dev clusters

Workload Readiness (Autopilot-specific)
- [ ] All containers have CPU/memory requests (mandatory - will cause pod rejections)
- [ ] No bare pods - all managed by Deployments/StatefulSets/Jobs
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] terminationGracePeriodSeconds ≤ 600s (10min Autopilot limit)
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] HPA/VPA configurations reviewed for 1.32 compatibility

Control Plane Timing Control
- [ ] Maintenance window configured for off-peak hours (only lever for Autopilot)
- [ ] Maintenance exclusion evaluated if upgrade deferral needed:
      - "No upgrades" (30-day max) for critical business periods
      - "No minor upgrades" to stay on 1.31 patches longer
- [ ] Scheduled upgrade notifications enabled for 72h advance warning

Ops Readiness
- [ ] Monitoring active (error rates, latency, throughput baselines from dev)
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware - Autopilot upgrades can't be paused mid-flight
- [ ] Rollback plan: minimal options (GKE manages nodes), focus on workload rollback
- [ ] Debug tooling ready: Cloud Logging, `kubectl debug` (no SSH access)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot Production 1.31→1.32

Control Plane Health
- [ ] [PROD-CLUSTER-1] control plane at 1.32: `gcloud container clusters describe CLUSTER-1 --region REGION --format="value(currentMasterVersion)"`
- [ ] [PROD-CLUSTER-2] control plane at 1.32: `gcloud container clusters describe CLUSTER-2 --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes eventually at 1.32 (GKE-managed, may take 30-60min after CP): `kubectl get nodes -o wide`
- [ ] System pods healthy: `kubectl get pods -n kube-system`

Workload Health Validation
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No failed pods due to missing resource requests: `kubectl get pods -A --field-selector=status.phase=Failed`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] HPA/VPA behavior normal (check scaling decisions): `kubectl get hpa -A`

Application & Integration Testing
- [ ] Load balancers and Ingress responding normally
- [ ] Application health checks passing
- [ ] API latency within baseline (watch for 1.32 behavioral changes)
- [ ] Database connections stable (if applicable)
- [ ] Service mesh (Istio/ASM) functioning if deployed
- [ ] Admission webhooks working (no pod creation failures)

Observability & Performance
- [ ] Cloud Logging collection active
- [ ] Cloud Monitoring metrics flowing
- [ ] Error rates ≤ pre-upgrade baseline
- [ ] Latency (p50/p95/p99) ≤ pre-upgrade baseline  
- [ ] No new ERROR/WARNING events: `kubectl get events -A --sort-by='.lastTimestamp' | tail -20`

Documentation & Cleanup
- [ ] Upgrade success documented in runbook/changelog
- [ ] Remove temporary maintenance exclusions if applied
- [ ] Update dev cluster upgrade strategy based on any production learnings
- [ ] Lessons learned captured for future minor version upgrades
```

## Key Autopilot Considerations

**What GKE manages for you:**
- Node pool upgrade strategy (always surge, ~20 nodes simultaneously)
- Node image and Kubernetes version lifecycle
- System component health and compatibility

**What you control:**
- **Timing**: Maintenance windows and exclusions
- **Workload readiness**: Resource requests (mandatory), PDBs, graceful shutdown
- **Validation**: Testing on dev clusters first

**Progressive rollout strategy:**
Since your dev clusters on Rapid are already at 1.32, you have a natural validation path. Any issues would have surfaced in dev first. When the Stable channel auto-upgrade begins next month, you'll be upgrading from a known-good version.

**If you need to defer the upgrade:**
```bash
# Block for 30 days max (critical business period)
gcloud container clusters update PROD-CLUSTER-1 \
  --region REGION \
  --add-maintenance-exclusion-name "defer-1.32" \
  --add-maintenance-exclusion-start-time YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-end-time YYYY-MM-DDTHH:MM:SSZ \
  --add-maintenance-exclusion-scope no_upgrades
```

Your setup with dev→Rapid and prod→Stable is an excellent pattern for safe upgrades!