# GKE Autopilot Upgrade Checklists

**Cluster Setup:** 4 Autopilot clusters | Dev: 2 clusters on Rapid | Prod: 2 clusters on Stable  
**Upgrade:** 1.31 → 1.32 (minor version) | Auto-upgrade timing: Next month

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot Clusters
- [ ] Clusters: 2 prod on Stable channel | Current: 1.31 | Target: 1.32

Compatibility & API Changes
- [ ] GKE 1.32 release notes reviewed for breaking changes
- [ ] Deprecated API usage checked (GKE console → Insights tab → "Deprecations and Issues")
- [ ] Alternative check: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Third-party operators compatible with K8s 1.32 (cert-manager, ingress controllers, monitoring)
- [ ] Admission webhooks tested against 1.32 (service mesh, policy engines)

Workload Readiness (Autopilot Requirements)
- [ ] All containers have resource requests (CPU/memory) - MANDATORY for Autopilot
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets
- [ ] PDBs configured for critical workloads (not overly restrictive — allow at least 1 disruption)
- [ ] terminationGracePeriodSeconds ≤ 10 minutes (Autopilot limit, 25s for Spot)
- [ ] StatefulSet data backups completed (application-level snapshots)
- [ ] Database/stateful operator versions support K8s 1.32

Dev Environment Validation (Rapid Channel Head Start)
- [ ] Dev clusters already on 1.32+ (Rapid gets versions ~2 weeks before Stable)
- [ ] Application compatibility validated in dev
- [ ] Performance regression testing completed
- [ ] CI/CD pipeline tested against 1.32

Observability & Operations
- [ ] Baseline metrics captured (error rates, latency, resource usage)
- [ ] Monitoring/alerting active (Cloud Monitoring, Prometheus, APM)
- [ ] Auto-upgrade timing reviewed (check maintenance windows if configured)
- [ ] Stakeholders notified of upcoming auto-upgrade window
- [ ] On-call schedule confirmed for upgrade period

Control Plane Timing (Main Lever for Autopilot)
- [ ] Maintenance windows configured for off-peak hours (if timing control needed)
- [ ] Consider maintenance exclusion if deferral needed:
      - "No upgrades" (30-day max, emergency deferrals only)
      - "No minor upgrades" (up to EoS, allows patches but blocks 1.31→1.32)
- [ ] Scheduled upgrade notifications enabled for 72h advance warning
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot Clusters

Cluster Health
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes at 1.32 (auto-managed by GKE in Autopilot)
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No admission webhook failures: `kubectl get events -A --field-selector type=Warning | grep webhook`

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No failed pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/load balancers responding (GKE manages these automatically)
- [ ] Application smoke tests passing

API and Compatibility
- [ ] No deprecated API warnings in cluster events: `kubectl get events -A --field-selector type=Warning`
- [ ] HPA/VPA scaling behavior normal (1.32 may change autoscaling algorithms)
- [ ] Custom operators still functional (restart if needed for API compatibility)

Observability Validation
- [ ] Metrics pipeline uninterrupted (Cloud Monitoring integration intact)
- [ ] Application logs flowing normally
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within acceptable range
- [ ] Resource utilization patterns normal (Autopilot may adjust node provisioning)

Multi-Cluster Consistency
- [ ] Both prod clusters upgraded successfully
- [ ] Dev and prod environments version-aligned (dev may be ahead on newer patches)
- [ ] Cross-cluster services (if any) functioning normally

Documentation
- [ ] Upgrade completion documented
- [ ] Any issues encountered logged for future upgrades
- [ ] Lessons learned shared with team
```

## Key Autopilot Differences

Since you're on Autopilot, note these simplifications:
- **No node pool management** — GKE handles all node upgrades automatically using surge strategy
- **Regional control plane** — No downtime during control plane upgrade
- **Auto-scaling** — Nodes provision/deprovision automatically during upgrade
- **Resource requests mandatory** — Missing requests cause pod failures (most common Autopilot upgrade issue)

## Timing Considerations

With your current setup:
- **Dev clusters (Rapid)** likely already upgraded to 1.32 — use them to validate compatibility
- **Prod clusters (Stable)** will auto-upgrade next month — you have time to prepare
- **Natural progression** — this setup gives you ~2-4 weeks of validation time between dev and prod

Consider enabling **scheduled upgrade notifications** to get 72h advance warning:
```bash
gcloud container clusters update CLUSTER_NAME \
  --region REGION \
  --enable-scheduled-upgrades
```