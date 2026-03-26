# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid channel) → 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (minor version)  
**Timeline:** Auto-upgrade scheduled next month

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot Clusters
- [ ] Dev clusters: ___ | Prod clusters: ___
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility & API Changes
- [ ] 1.32 release notes reviewed for breaking changes (https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] No deprecated API usage in prod workloads:
      - [ ] Check GKE deprecation insights in console (Insights tab)
      - [ ] Run: kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
- [ ] Third-party operators (Istio, cert-manager, etc.) support K8s 1.32
- [ ] CI/CD pipelines tested against 1.32 (use dev clusters for validation)

Workload Readiness (Autopilot Requirements)
- [ ] All containers have resource requests defined (CPU & memory - mandatory for Autopilot)
- [ ] PDBs configured for critical workloads (not overly restrictive - max 1hr respect during upgrade)
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] terminationGracePeriodSeconds ≤ 600s for regular pods (Autopilot limit)
- [ ] terminationGracePeriodSeconds ≤ 25s for Spot pods (Autopilot limit)
- [ ] StatefulSet data backed up if applicable

Dev Cluster Validation (Complete Before Prod)
- [ ] Dev clusters already upgraded to 1.32 (Rapid channel gets it first)
- [ ] Application smoke tests passing on dev 1.32 clusters
- [ ] Performance baseline confirmed (latency, throughput within range)
- [ ] No admission webhook failures or API compatibility issues
- [ ] Service mesh (if used) functioning properly on 1.32

Production Timing Control
- [ ] Maintenance window configured for prod clusters (off-peak hours):
      gcloud container clusters update PROD_CLUSTER_NAME \
        --region REGION \
        --maintenance-window-start "2024-XX-XXTXX:XX:XXZ" \
        --maintenance-window-duration 4h \
        --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"
- [ ] Consider maintenance exclusion if timing needs adjustment:
      - "no upgrades" (30-day max) for temporary deferral
      - "no minor upgrades" (up to EoS) for patch-only mode
- [ ] Rollout sequence: ensure both prod clusters don't upgrade simultaneously

Ops Readiness
- [ ] Monitoring dashboards active (error rates, latency baselines captured)
- [ ] On-call team aware of scheduled upgrade window
- [ ] Stakeholders notified of expected upgrade timing
- [ ] Rollback plan documented (limited options for control plane downgrades)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot Clusters

Control Plane Health
- [ ] Prod cluster 1 at 1.32: gcloud container clusters describe CLUSTER_1 --region REGION --format="value(currentMasterVersion)"
- [ ] Prod cluster 2 at 1.32: gcloud container clusters describe CLUSTER_2 --region REGION --format="value(currentMasterVersion)"
- [ ] System pods healthy: kubectl get pods -n kube-system
- [ ] No upgrade operations in progress: gcloud container operations list --region REGION

Node Health (Autopilot Managed)
- [ ] All nodes Ready: kubectl get nodes
- [ ] No nodes stuck in upgrade state
- [ ] Node versions align with control plane (Autopilot handles this automatically)

Workload Health - Cluster 1
- [ ] All deployments at desired replica count: kubectl get deployments -A
- [ ] No CrashLoopBackOff pods: kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
- [ ] StatefulSets fully ready: kubectl get statefulsets -A
- [ ] Load balancers responding (ping external endpoints)
- [ ] Application health checks passing

Workload Health - Cluster 2
- [ ] All deployments at desired replica count: kubectl get deployments -A
- [ ] No CrashLoopBackOff pods: kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded
- [ ] StatefulSets fully ready: kubectl get statefulsets -A
- [ ] Load balancers responding (ping external endpoints)
- [ ] Application health checks passing

API & Compatibility Validation
- [ ] No admission webhook errors in events: kubectl get events -A --field-selector type=Warning | grep webhook
- [ ] HPA/VPA scaling behavior normal (check for algorithm changes in 1.32)
- [ ] Service mesh control plane (if applicable) handling new API version
- [ ] CI/CD deployments working against upgraded clusters

Observability & Performance
- [ ] Metrics collection active, no gaps in dashboards
- [ ] Logs flowing to aggregation systems
- [ ] API latency within pre-upgrade baseline (p95, p99)
- [ ] Application error rates ≤ pre-upgrade baseline
- [ ] No unexpected 503s from API server

Documentation & Cleanup
- [ ] Upgrade completion logged in change management system
- [ ] Any temporary maintenance exclusions removed (if applied)
- [ ] Next upgrade timeline noted (1.32 → 1.33 when available in Stable)
- [ ] Lessons learned documented for future upgrades
```

## Key Notes for Your Setup

**Progressive validation:** Since dev is on Rapid channel, you'll get 1.32 there first (~2-4 weeks before Stable). Use this natural progression to validate workload compatibility before prod auto-upgrades.

**Autopilot simplifications:** No node pool management needed — GKE handles all node upgrades automatically with surge strategy. Focus on control plane timing and workload readiness.

**Timing control:** The maintenance window is your primary lever for **when** the upgrade happens. Auto-upgrades respect maintenance windows, but manual upgrades bypass them entirely.

**Resource requests reminder:** Double-check that all containers have CPU/memory requests — Autopilot will reject pods without them, and upgrades can expose previously hidden missing requests.

**Limited rollback:** Control plane minor version downgrades require GKE support. Your best protection is thorough dev cluster validation before prod upgrades.