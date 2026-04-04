# GKE Autopilot Upgrade Checklists

**Your setup:** 4 Autopilot clusters | Dev: 2 clusters on Rapid | Prod: 2 clusters on Stable | Upcoming: 1.31→1.32 auto-upgrade

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31→1.32
- [ ] Clusters: Dev (Rapid) + Prod (Stable) | All Autopilot | Target: 1.32

Compatibility & Planning
- [ ] 1.32 already validated in dev clusters on Rapid channel
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE 1.32 release notes reviewed for breaking changes
- [ ] Third-party operators/controllers compatibility verified with K8s 1.32
- [ ] Admission webhooks (cert-manager, policy controllers) support K8s 1.32

Workload Readiness (Autopilot-specific)
- [ ] All containers have resource requests (CPU/memory) - mandatory for Autopilot
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] terminationGracePeriodSeconds ≤ 10 minutes (600s) for regular pods
- [ ] terminationGracePeriodSeconds ≤ 25 seconds for Spot pods (if using)
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] StatefulSet data backed up, PV reclaim policies verified

Autopilot Constraints Verified
- [ ] All workloads use supported container images
- [ ] No privileged containers or host mounts
- [ ] Network policies compatible with Autopilot
- [ ] Ingress controllers compatible with K8s 1.32

Auto-Upgrade Controls
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Optional: "No minor upgrades" exclusion if you want manual control over 1.32 timing
      (allows patches, blocks minor version auto-upgrades until you're ready)
- [ ] Scheduled upgrade notifications enabled for 72h advance warning

Multi-Cluster Validation Strategy
- [ ] Dev clusters (Rapid) already on 1.32 — validate workloads thoroughly
- [ ] Smoke tests passing on dev after 1.32 upgrade
- [ ] Performance baselines established on dev clusters
- [ ] Any issues identified in dev resolved before prod upgrade

Ops Readiness
- [ ] Monitoring active (Cloud Operations suite)
- [ ] Baseline metrics captured (error rates, latency, pod restart rates)
- [ ] Upgrade timing communicated to stakeholders
- [ ] On-call team aware — Autopilot upgrades are fully managed but workload issues can still occur
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.32

Cluster Health (per cluster)
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes at 1.32 (managed automatically by Autopilot)
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No node NotReady status: `kubectl get nodes`

Workload Health (per cluster)
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Services and Ingress responding
- [ ] Application health checks passing

Autopilot-Specific Validation
- [ ] Pod resource requests still respected (no rejected pods due to missing requests)
- [ ] Autopilot node provisioning working (new pods scheduling successfully)
- [ ] No admission webhook failures blocking pod creation
- [ ] GKE-managed certificates renewed if using Google-managed SSL

Cross-Cluster Validation
- [ ] Both prod clusters upgraded successfully
- [ ] Load balancer traffic distributed correctly across clusters
- [ ] Service mesh control plane (if applicable) compatible with 1.32
- [ ] Cross-cluster networking (if applicable) functioning

Observability
- [ ] Cloud Monitoring metrics collection active
- [ ] Cloud Logging ingestion normal
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline
- [ ] No unusual pod eviction patterns

Documentation
- [ ] Upgrade completion documented
- [ ] Any issues encountered and resolutions captured
- [ ] Update runbooks/playbooks with 1.32-specific changes
```

## Key Autopilot Differences

**What you DON'T need to worry about:**
- Node pool upgrade strategies (surge/blue-green) — handled automatically
- Compute quota for surge nodes — managed by Google
- maxSurge/maxUnavailable settings — not applicable
- SSH access to nodes for troubleshooting

**What you DO need to focus on:**
- **Resource requests are mandatory** — any pod without CPU/memory requests will be rejected
- **Validation in dev first** — your Rapid clusters are the perfect canary for Stable
- **PDB limits** — Autopilot respects PDBs for up to 1 hour, then force-evicts
- **Grace period limits** — 10 min max for regular pods, 25 sec for Spot

Since your dev clusters on Rapid should already be on 1.32, use them to validate everything works before the Stable clusters auto-upgrade. This is exactly the right channel strategy for progressive validation!