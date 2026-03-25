# GKE Autopilot Upgrade Checklists
**Environment:** 4 Autopilot clusters | Dev: 2 clusters (Rapid) | Prod: 2 clusters (Stable)  
**Upgrade:** 1.31 → 1.32 (minor version upgrade)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot Clusters
Environment: Dev (2 clusters, Rapid) | Prod (2 clusters, Stable)
Target: 1.31 → 1.32

Compatibility & Planning
- [ ] Target version 1.32 available in Stable channel: `gcloud container get-server-config --region REGION --format="yaml(channels.STABLE)"`
- [ ] Dev clusters already on 1.32 and stable (validate before prod upgrade)
- [ ] GKE 1.32 release notes reviewed for breaking changes
- [ ] No deprecated API usage: Check GKE deprecation insights in console (Insights tab)
- [ ] Third-party operators compatible with K8s 1.32 (cert-manager, ingress controllers, etc.)

Workload Readiness (Critical for Autopilot)
- [ ] ALL containers have resource requests (mandatory - pods rejected without them)
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] terminationGracePeriodSeconds ≤ 600s (10min limit for most pods, 25s for Spot)
- [ ] StatefulSet data backed up, PV reclaim policies verified (Retain, not Delete)
- [ ] Database/stateful workload health checks ready

Autopilot Upgrade Controls
- [ ] Maintenance windows configured for off-peak hours (control plane timing only)
- [ ] Consider maintenance exclusions if needed:
      - "No upgrades" (30-day max) for critical periods
      - "No minor upgrades" (up to EoS) to defer 1.32 until ready
- [ ] Auto-upgrade notifications enabled for 72h advance warning

Operational Readiness
- [ ] Dev clusters serving as canaries (validate 1.32 behavior first)
- [ ] Monitoring baseline captured (error rates, latency, pod restart frequency)
- [ ] Cloud Logging access ready (no SSH in Autopilot - debug via logs only)
- [ ] Team aware: Autopilot uses GKE-managed surge upgrades (no node pool control)
- [ ] Rollback plan: Control plane patches can be downgraded, minor versions need GKE support

Dev Validation (Complete Before Prod)
- [ ] Dev cluster 1: Upgrade validated, workloads stable for 48+ hours
- [ ] Dev cluster 2: Upgrade validated, workloads stable for 48+ hours
- [ ] Application smoke tests passing on 1.32
- [ ] No API behavioral changes affecting workloads
- [ ] System component health (CoreDNS, metrics-server) stable
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot

Cluster Health
- [ ] Prod cluster 1: Control plane at 1.32: `gcloud container clusters describe CLUSTER1 --region REGION --format="value(currentMasterVersion)"`
- [ ] Prod cluster 2: Control plane at 1.32: `gcloud container clusters describe CLUSTER2 --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes auto-upgraded (Autopilot manages this): `kubectl get nodes --context=CLUSTER1_CONTEXT` and `kubectl get nodes --context=CLUSTER2_CONTEXT`
- [ ] System pods healthy in kube-system: `kubectl get pods -n kube-system --context=CLUSTER1_CONTEXT`

Workload Health (Both Prod Clusters)
- [ ] All deployments at desired replica count: `kubectl get deployments -A --context=CLUSTER_CONTEXT`
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running --context=CLUSTER_CONTEXT`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A --context=CLUSTER_CONTEXT`
- [ ] Ingress/LoadBalancer services responding
- [ ] Database connections stable (no authentication/TLS issues)

Application Validation
- [ ] Health checks passing across all services
- [ ] API response times within baseline (check monitoring dashboards)
- [ ] Error rates ≤ pre-upgrade baseline
- [ ] No admission webhook failures (common after control plane upgrades)
- [ ] Resource requests still honored (Autopilot requirement)

Monitoring & Observability
- [ ] Cloud Logging collection active (no gaps during upgrade window)
- [ ] Metrics pipeline healthy in Cloud Monitoring/Prometheus
- [ ] Alerting rules functioning
- [ ] No new error patterns in logs

Documentation & Cleanup
- [ ] Upgrade completion logged in team changelog
- [ ] Remove temporary maintenance exclusions (if applied)
- [ ] Update infrastructure-as-code to reflect 1.32 (if version-pinned)
- [ ] Lessons learned documented for next upgrade cycle
```

## Key Autopilot Considerations

**Resource Requests:** Autopilot will reject pods without resource requests. This is the #1 cause of post-upgrade failures.

**Upgrade Strategy:** Autopilot uses GKE-managed surge upgrades. You can't configure maxSurge/maxUnavailable, but you can control timing via maintenance windows and exclusions.

**Termination Limits:** Autopilot enforces stricter termination grace periods (10min max for most pods, 25s for Spot). Ensure your workloads can shut down within these limits.

**Dev-First Validation:** Since your dev clusters are on Rapid channel, they're your natural canaries. Validate 1.32 stability there before it reaches your Stable prod clusters.

**Regional High Availability:** All Autopilot clusters are regional, so control plane upgrades won't cause API downtime—the cluster remains available throughout the upgrade.

Use this staged approach: validate dev clusters → apply any needed maintenance exclusions to prod → let prod auto-upgrade when you're ready → validate prod clusters.