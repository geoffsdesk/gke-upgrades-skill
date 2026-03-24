# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid), 2 prod clusters (Stable) | 1.31 → 1.32

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot Clusters
- [ ] Dev clusters: ___ | Prod clusters: ___ 
- [ ] Current version: 1.31 | Target version: 1.32
- [ ] Channel config: Dev=Rapid, Prod=Stable ✓

Compatibility
- [ ] 1.32 available in Stable channel: `gcloud container get-server-config --zone ZONE --format="yaml(channels.STABLE)"`
- [ ] No deprecated API usage in prod clusters (check GKE deprecation insights dashboard)
- [ ] GKE release notes reviewed for 1.31 → 1.32 breaking changes
- [ ] Kubernetes 1.32 changelog reviewed for upstream changes
- [ ] Third-party operators/controllers compatible with 1.32 (cert-manager, ingress controllers, etc.)
- [ ] Admission webhooks tested against 1.32 on dev clusters

Workload Readiness (Autopilot-specific)
- [ ] All containers have resource requests (CPU/memory) - mandatory for Autopilot
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by controllers (Deployments, StatefulSets, etc.)
- [ ] terminationGracePeriodSeconds ≤ 600s (10 min limit for Autopilot)
- [ ] StatefulSet data backed up, PV reclaim policies verified as "Retain"
- [ ] HPA/VPA configurations reviewed for 1.32 compatibility
- [ ] Service mesh (if used) compatible with 1.32

Dev Cluster Validation (should already be on 1.32+)
- [ ] Dev clusters upgraded and stable on 1.32+ (Rapid channel advantage)
- [ ] Application smoke tests passing on dev
- [ ] No regression in metrics/logs on dev
- [ ] Workload startup times within expected range
- [ ] Any 1.32-specific issues identified and mitigated

Infrastructure & Timing
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Consider maintenance exclusion if timing needs adjustment:
      - "No upgrades" (30-day max) for code freeze periods
      - Coordinate with any upcoming releases or critical business periods
- [ ] Auto-upgrade notifications enabled for 72h advance notice
- [ ] Rollout sequence: confirm dev validates before prod auto-upgrades

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring dashboards)
- [ ] Baseline metrics captured (error rates, latency, pod startup time)
- [ ] Upgrade timeline communicated to stakeholders
- [ ] On-call team aware of upgrade window
- [ ] Runbook ready for common post-upgrade issues (webhook failures, API changes)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot Clusters

Cluster Health (per cluster)
- [ ] Cluster 1: Control plane at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] Cluster 2: Control plane at 1.32
- [ ] Nodes automatically upgraded (Autopilot managed): `kubectl get nodes -o wide`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No authentication/authorization issues with kubectl access

Workload Health (per cluster)
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] All PVCs bound: `kubectl get pvc -A`
- [ ] Ingress/load balancers responding
- [ ] Application health checks passing
- [ ] HPA scaling working correctly: `kubectl get hpa -A`

Post-Upgrade Common Issues (Autopilot)
- [ ] Resource requests still valid (no pods stuck due to Autopilot resource requirements)
- [ ] No admission webhook failures: `kubectl get events -A --field-selector type=Warning | grep webhook`
- [ ] API latency normal (check Cloud Monitoring GKE dashboards)
- [ ] No unexpected pod restarts: `kubectl get events -A --field-selector reason=Killing --sort-by='.lastTimestamp' | tail -10`

Observability & Performance
- [ ] Metrics pipeline active, no collection gaps
- [ ] Logs flowing to Cloud Logging
- [ ] Error rates within pre-upgrade baseline
- [ ] API server latency (p50/p95) within baseline
- [ ] Pod startup times normal for Autopilot (typically 10-30s for cold starts)

Cleanup & Documentation
- [ ] No manual cleanup needed (Autopilot handles node lifecycle)
- [ ] Upgrade success documented
- [ ] Any issues or performance changes noted
- [ ] Dev cluster lessons applied to prod upgrade plan
- [ ] Next upgrade timeline reviewed (Stable channel cadence)
```

## Key Autopilot Considerations

**Timing advantage:** Your dev clusters on Rapid should upgrade to 1.32 weeks before prod (Stable), giving you validation time. Use dev as your canary.

**No node pool management:** Skip all node pool upgrade strategies—Autopilot handles this automatically with surge upgrades.

**Resource requests critical:** Ensure all containers have CPU/memory requests. Missing requests cause pod rejection in Autopilot.

**Faster troubleshooting:** Use `kubectl debug` and Cloud Logging for debugging—no SSH access to nodes.

**Maintenance windows:** Still valuable for controlling timing of control plane upgrades, even though you don't manage nodes directly.

Would you like me to create a specific runbook for your environment or help you set up the maintenance windows for better upgrade timing control?