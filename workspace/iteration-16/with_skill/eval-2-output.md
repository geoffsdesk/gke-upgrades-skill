# GKE Autopilot Upgrade Checklists
**Environment:** 2 dev clusters (Rapid) + 2 prod clusters (Stable)  
**Upgrade:** 1.31 → 1.32 (minor version)  
**Timeline:** Auto-upgrade next month

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
Environment: 2 dev (Rapid) + 2 prod (Stable)

Compatibility & Breaking Changes
- [ ] Review GKE 1.32 release notes for breaking changes
- [ ] Check deprecated API usage in all clusters:
      `kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated`
- [ ] Verify GKE deprecation insights dashboard (Console → GKE → Insights)
- [ ] Kubernetes 1.32 upstream changes reviewed (especially if using raw K8s APIs)

Dev Environment Validation (Rapid channel should upgrade first)
- [ ] Dev clusters already on 1.32 from Rapid channel auto-upgrades
- [ ] Dev workloads tested and stable on 1.32
- [ ] Application health confirmed in dev after 1.32 upgrade
- [ ] No new pod admission failures or resource request issues
- [ ] CI/CD pipelines working correctly against 1.32 API

Workload Readiness (All Clusters)
- [ ] All containers have resource requests (mandatory in Autopilot):
      `kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].resources.requests}{"\n"}{end}' | grep -v cpu`
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by controllers:
      `kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'`
- [ ] terminationGracePeriodSeconds ≤ 10 minutes for regular pods, ≤ 25 seconds for Spot (Autopilot limits)
- [ ] StatefulSet data backed up, PV reclaim policies verified
- [ ] Third-party operators compatible with K8s 1.32 (cert-manager, ingress controllers, etc.)

Production Timing Control
- [ ] Maintenance windows configured for off-peak hours on prod clusters
- [ ] Consider maintenance exclusion if upgrade timing needs control:
      - "No minor upgrades" (allows patches, up to 1.31 EoS)
      - "No upgrades" (30-day max, for critical business periods)
- [ ] Scheduled upgrade notifications enabled for 72h advance warning:
      `gcloud container clusters update CLUSTER --send-scheduled-upgrade-notifications`

Observability & Ops
- [ ] Monitoring dashboards active (error rates, latency, pod restart counts)
- [ ] Baseline metrics captured from current 1.31 performance
- [ ] Alert thresholds reviewed (some may need adjustment for 1.32)
- [ ] On-call coverage planned during auto-upgrade window
- [ ] Rollback plan documented (limited options for auto-upgrades)
- [ ] Stakeholders notified of upcoming prod upgrades

Multi-Cluster Considerations
- [ ] Both prod clusters will upgrade around the same time (Stable channel)
- [ ] No rollout sequencing configured (dev/prod on different channels)
- [ ] Cross-cluster dependencies identified (if one cluster serves the other)
- [ ] Load balancing strategy accounts for potential brief disruptions
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.32
Run for each cluster after auto-upgrade completes

Cluster Health
- [ ] Control plane version: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] Nodes upgraded automatically by Autopilot (verify in Console)
- [ ] All nodes Ready: `kubectl get nodes`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] Autopilot system pods stable: `kubectl get pods -n gke-system`

Workload Health  
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No pods stuck in CrashLoopBackOff or Pending: 
      `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] DaemonSets running on all nodes: `kubectl get daemonsets -A`
- [ ] Services and endpoints healthy: `kubectl get svc,endpoints -A`

Application Validation
- [ ] Application health checks passing
- [ ] Ingress/load balancers responding correctly
- [ ] External traffic routing properly
- [ ] Database connections stable (if applicable)
- [ ] Batch jobs completing successfully
- [ ] No resource request admission failures

Autopilot-Specific Checks
- [ ] Pod rightsizing recommendations stable (check Console → GKE → Workloads)
- [ ] No new "resource requests required" errors in events
- [ ] Cluster autoscaling behavior normal (pods scheduling on appropriate node types)
- [ ] GPU/TPU workloads functioning if applicable

Observability
- [ ] Metrics collection resumed (no gaps during upgrade)
- [ ] Log aggregation working correctly  
- [ ] Error rates within pre-upgrade baseline
- [ ] API latency (p50/p95/p99) normal compared to pre-upgrade
- [ ] No new 403/admission controller errors
- [ ] Custom metrics and dashboards displaying correctly

Multi-Cluster Validation
- [ ] Cross-cluster communication working (if applicable)
- [ ] Load distribution normal across both prod clusters
- [ ] Service mesh connectivity stable (if using Istio/ASM)
- [ ] Both clusters showing consistent behavior

Documentation & Cleanup
- [ ] Upgrade completion documented in changelog
- [ ] Remove temporary maintenance exclusions if applied
- [ ] Update internal runbooks with any 1.32-specific changes
- [ ] Lessons learned captured for next upgrade cycle
```

## Key Notes for Your Setup

**Channel Strategy:** Your dev→prod flow (Rapid→Stable) is excellent. Dev clusters should upgrade to 1.32 weeks before prod, giving you time to catch issues.

**Auto-upgrade Control:** Since these are auto-upgrades, your main control levers are:
- Maintenance windows (timing)  
- Maintenance exclusions (temporary blocking)
- The dev clusters as your canary environment

**Autopilot Advantages:** No node pool management needed - focus on workload readiness and timing. The upgrade will be less disruptive than Standard clusters since Google manages the infrastructure layer.

**Timeline:** Typical progression is Rapid (dev) gets 1.32 first, then 4-6 weeks later Stable (prod) gets it. Use this gap to validate in dev.