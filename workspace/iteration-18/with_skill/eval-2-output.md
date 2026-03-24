# GKE Autopilot Upgrade Checklists

**Environment:** 2 dev clusters (Rapid channel) + 2 prod clusters (Stable channel)  
**Upgrade:** 1.31 → 1.32 (minor version upgrade)  
**Timeline:** Next month (auto-upgrade)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Clusters: 2 dev (Rapid) + 2 prod (Stable) | All Autopilot
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility & Version Readiness
- [ ] 1.32 availability confirmed in Stable channel: `gcloud container get-server-config --region REGION --format="yaml(channels)"`
- [ ] GKE 1.32 release notes reviewed for breaking changes (https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] No deprecated API usage detected in dev clusters: Check GKE deprecation insights dashboard
- [ ] Dev clusters (Rapid) already upgraded to 1.32 and stable for 2+ weeks
- [ ] Third-party operators/controllers compatibility verified with 1.32 in dev

Workload Readiness (Autopilot-specific)
- [ ] All containers have resource requests (mandatory for Autopilot) - verify no pods rejected
- [ ] PDBs configured for critical workloads (not overly restrictive - max disruption 1 hour)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets
- [ ] terminationGracePeriodSeconds ≤ 600s (10 min limit for most pods, 25s for Spot)
- [ ] StatefulSet application backups completed for prod clusters
- [ ] Database operators (if any) confirmed compatible with K8s 1.32

Infrastructure & Timing
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Consider maintenance exclusion if upgrade timing conflicts:
      - "No upgrades" (30-day max) for critical periods
      - "No minor upgrades" to allow patches but defer 1.32
- [ ] Auto-upgrade target confirmed: `gcloud container clusters get-upgrade-info CLUSTER --region REGION`
- [ ] Scheduled upgrade notifications enabled (72h advance warning via Cloud Logging)

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring alerts configured)
- [ ] Baseline metrics captured from dev clusters post-1.32 upgrade
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call coverage arranged for prod upgrade window
- [ ] Rollback plan documented (limited options for control plane)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Cluster Health
- [ ] Prod cluster 1 control plane at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] Prod cluster 2 control plane at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes auto-upgraded by GKE (Autopilot manages this automatically)
- [ ] All nodes Ready: `kubectl get nodes` (both clusters)
- [ ] System pods healthy: `kubectl get pods -n kube-system` (both clusters)

Workload Health (Both Prod Clusters)
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No failed pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Services and ingress responding to health checks
- [ ] Application smoke tests passing
- [ ] Database connectivity verified (if applicable)

API and Application Compatibility
- [ ] No admission webhook failures: `kubectl get events -A --field-selector type=Warning | grep webhook`
- [ ] HPA/VPA scaling behavior normal: `kubectl describe hpa -A`
- [ ] No deprecated API warnings in applications
- [ ] Custom controllers/operators functioning normally

Observability
- [ ] Cloud Monitoring metrics collection active
- [ ] Application logs flowing normally
- [ ] Error rates within baseline (compare to dev post-upgrade)
- [ ] API latency p95 within acceptable range
- [ ] No new alerts firing related to K8s version change

Security & Compliance
- [ ] Pod Security Standards enforcement unchanged
- [ ] NetworkPolicies functioning as expected
- [ ] RBAC permissions intact
- [ ] Service mesh (if applicable) control plane compatible with 1.32

Cleanup & Documentation
- [ ] Upgrade completion documented
- [ ] Any temporary maintenance exclusions removed
- [ ] Dev/prod version alignment confirmed (both on 1.32)
- [ ] Lessons learned from dev upgrade applied successfully
```

## Key Autopilot Considerations

**What GKE manages for you:**
- Node pool upgrades (automatic, surge-based)
- Node provisioning and replacement
- System component compatibility
- Driver updates and patches

**What you control:**
- Control plane upgrade timing (via maintenance windows/exclusions)
- Workload readiness and PDB configuration
- Application-level compatibility testing

**Validation Strategy:**
Since your dev clusters on Rapid should upgrade to 1.32 first, use them as your staging environment. Run your full application test suite on dev after they upgrade, then proceed with prod when confident.

**Timeline Recommendation:**
1. Dev clusters upgrade automatically on Rapid (likely already happened or happening soon)
2. Validate workloads on dev for 2+ weeks
3. Let prod clusters auto-upgrade on Stable OR manually trigger if you want to control exact timing within your maintenance window

Would you like me to help you configure maintenance windows or exclusions for your prod clusters to control the upgrade timing?