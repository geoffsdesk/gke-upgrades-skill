# GKE Autopilot Upgrade Checklists
**Clusters:** 2 dev (Rapid) + 2 prod (Stable) | **Upgrade:** 1.31 → 1.32 (minor version)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
Environment: 2 dev clusters (Rapid) + 2 prod clusters (Stable)

Compatibility & API Changes
- [ ] Target version 1.32 confirmed available in Stable channel
- [ ] Deprecated API usage checked via GKE deprecation insights dashboard
- [ ] Kubernetes 1.32 release notes reviewed for breaking changes
- [ ] Third-party operators/controllers verified compatible with 1.32
- [ ] Admission webhooks (cert-manager, policy controllers) tested against 1.32

Workload Readiness (Critical for Autopilot)
- [ ] ALL containers have resource requests specified (CPU/memory) - mandatory for Autopilot
- [ ] PDBs configured for critical workloads (not overly restrictive - GKE respects for 1h max)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds ≤ 10 minutes (600s limit for most pods in Autopilot)
- [ ] StatefulSet data backed up, PV reclaim policies verified as "Retain"
- [ ] Database operators (if any) confirmed compatible with Kubernetes 1.32

Dev Environment Validation (Rapid channel - likely already upgraded)
- [ ] Dev clusters already on 1.32? Check: `gcloud container clusters describe DEV_CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"`
- [ ] If dev on 1.32: workload health validated, no regressions observed
- [ ] If dev still on 1.31: plan to validate 1.32 in dev before prod auto-upgrade

Control Plane Timing (Main lever for Autopilot)
- [ ] Prod maintenance windows configured for off-peak hours
- [ ] Maintenance exclusion strategy chosen if upgrade timing needs control:
      - "No upgrades" (30-day max) for complete freeze during critical periods
      - "No minor upgrades" to stay on 1.31 patches until manual minor upgrade
- [ ] Auto-upgrade timeline reviewed - GKE will upgrade during maintenance window

Infrastructure & Ops
- [ ] Regional clusters confirmed (all Autopilot clusters are regional - CP stays available)
- [ ] Monitoring baseline captured (error rates, latency, throughput)
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware and available during expected auto-upgrade window
- [ ] Rollback plan documented (limited options - mainly workload-level rollbacks)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Cluster Health
- [ ] Both prod clusters at 1.32: `gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes auto-upgraded by GKE (Autopilot manages this): `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] No admission webhook failures: `kubectl get events -A --field-selector reason=FailedCreate | grep webhook`

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No pods stuck in CrashLoopBackOff: `kubectl get pods -A | grep CrashLoop`
- [ ] No pods stuck Pending due to missing resource requests: `kubectl get pods -A --field-selector=status.phase=Pending`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/Gateway API resources responding correctly
- [ ] Application health checks and smoke tests passing

API & Compatibility Validation
- [ ] No deprecated API usage warnings: `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] HPA/VPA behavior unchanged: `kubectl describe hpa -A` (check for scaling decision changes)
- [ ] Custom resources and CRDs functioning: `kubectl get crd` and test key workflows
- [ ] Service mesh (if applicable) control plane compatible with 1.32

Observability & Performance
- [ ] Metrics pipeline active, no collection gaps during upgrade
- [ ] Logs flowing correctly to Cloud Logging
- [ ] Error rates within pre-upgrade baseline
- [ ] API latency (p50/p95/p99) within acceptable range
- [ ] No unexpected 503 errors or admission failures

Cleanup & Documentation
- [ ] Upgrade success documented in changelog
- [ ] Dev/prod version alignment confirmed (both environments on 1.32)
- [ ] Next upgrade timeline reviewed (Stable channel cadence)
- [ ] Lessons learned captured for future upgrades
```

## Key Autopilot-Specific Notes

**Resource Requests Critical:** Unlike Standard clusters, Autopilot REQUIRES resource requests on all containers. Pods without requests will fail to schedule post-upgrade.

**Limited Upgrade Control:** You can't control node pool upgrade strategy (GKE uses surge automatically). Your main levers are:
- Maintenance windows for timing
- Maintenance exclusions for deferral ("no minor upgrades" if you want to stay on 1.31 patches)

**Progressive Validation:** Since your dev clusters on Rapid channel likely upgraded to 1.32 weeks ago, validate workload health there before prod auto-upgrades. This is your natural staging environment.

**Termination Limits:** Autopilot enforces stricter termination limits (10min for most pods, 25s for Spot). Ensure graceful shutdown fits within these bounds.

Would you like me to create a specific runbook with `gcloud` commands for any maintenance window or exclusion configuration?