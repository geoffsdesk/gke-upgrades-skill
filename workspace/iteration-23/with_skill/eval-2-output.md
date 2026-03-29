# GKE Autopilot Upgrade Checklists
**Environment:** 4 Autopilot clusters | Dev: 2 clusters (Rapid) | Prod: 2 clusters (Stable)  
**Upgrade:** Control plane 1.31 → 1.32 (minor version)  
**Timeline:** Next month (auto-upgrade)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Clusters: [DEV-CLUSTER-1], [DEV-CLUSTER-2] (Rapid) | [PROD-CLUSTER-1], [PROD-CLUSTER-2] (Stable)

Compatibility & Breaking Changes
- [ ] GKE 1.32 release notes reviewed for breaking changes from 1.31
- [ ] Deprecated API usage checked in all clusters:
  ```bash
  kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
  ```
- [ ] GKE deprecation insights dashboard reviewed (Console → Clusters → Insights tab)
- [ ] Third-party operators compatible with K8s 1.32 (cert-manager, ingress controllers, etc.)
- [ ] Admission webhooks tested against 1.32 API changes

Workload Readiness (Critical for Autopilot)
- [ ] ALL containers have resource requests configured (mandatory):
  ```bash
  kubectl get pods -A -o json | jq '.items[] | select(.spec.containers[].resources.requests == null) | {ns:.metadata.namespace, name:.metadata.name}'
  ```
- [ ] PDBs configured for critical workloads (not overly restrictive):
  ```bash
  kubectl get pdb -A -o wide
  ```
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets:
  ```bash
  kubectl get pods -A -o json | jq -r '.items[] | select(.metadata.ownerReferences | length == 0) | "\(.metadata.namespace)/\(.metadata.name)"'
  ```
- [ ] terminationGracePeriodSeconds ≤ 600s (10min limit for most Autopilot pods, 25s for Spot)
- [ ] StatefulSet backups completed for production data
- [ ] Database operators (if any) verified compatible with K8s 1.32

Channel Strategy Validation
- [ ] Dev clusters on Rapid already at 1.32 (natural progression validation):
  ```bash
  gcloud container clusters describe DEV-CLUSTER-1 --region REGION --format="value(currentMasterVersion)"
  ```
- [ ] Workload compatibility validated in dev environment
- [ ] Performance baseline established in prod before upgrade

Upgrade Control (if needed)
- [ ] Maintenance windows configured for prod clusters (off-peak hours):
  ```bash
  gcloud container clusters update PROD-CLUSTER --region REGION \
    --maintenance-window-start "YYYY-MM-DDTHH:MM:SSZ" \
    --maintenance-window-duration 4h \
    --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SA"
  ```
- [ ] Consider temporary exclusion if timing is problematic (up to 30 days):
  ```bash
  gcloud container clusters update PROD-CLUSTER --region REGION \
    --add-maintenance-exclusion-name "defer-upgrade" \
    --add-maintenance-exclusion-start YYYY-MM-DDTHH:MM:SSZ \
    --add-maintenance-exclusion-end YYYY-MM-DDTHH:MM:SSZ \
    --add-maintenance-exclusion-scope no_upgrades
  ```

Ops Readiness
- [ ] Monitoring dashboards active for all 4 clusters
- [ ] Baseline metrics captured (error rates, latency, throughput)
- [ ] Upgrade notifications configured (72h advance warning):
  ```bash
  gcloud container clusters update CLUSTER --region REGION --send-scheduled-upgrade-notifications
  ```
- [ ] On-call team aware of upgrade timeline
- [ ] Rollback plan documented (limited options for control plane downgrades)
```

## Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Cluster Health (All 4 clusters)
- [ ] Control plane at 1.32:
  ```bash
  for cluster in DEV-CLUSTER-1 DEV-CLUSTER-2 PROD-CLUSTER-1 PROD-CLUSTER-2; do
    echo "=== $cluster ==="
    gcloud container clusters describe $cluster --region REGION --format="value(currentMasterVersion)"
  done
  ```
- [ ] System pods healthy in kube-system:
  ```bash
  kubectl get pods -n kube-system --context CLUSTER-CONTEXT
  ```
- [ ] No stuck PDBs:
  ```bash
  kubectl get pdb -A --context CLUSTER-CONTEXT
  ```

Autopilot-Specific Validation
- [ ] Node pools automatically upgraded (GKE-managed):
  ```bash
  kubectl get nodes -o wide --context CLUSTER-CONTEXT
  ```
- [ ] All pods have required resource requests (Autopilot enforcement):
  ```bash
  kubectl get pods -A --field-selector=status.phase=Pending --context CLUSTER-CONTEXT
  ```
- [ ] No resource request violations causing pod rejections

Workload Health (Per cluster)
- [ ] All deployments at desired replica count:
  ```bash
  kubectl get deployments -A --context CLUSTER-CONTEXT
  ```
- [ ] No CrashLoopBackOff or long-Pending pods:
  ```bash
  kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded --context CLUSTER-CONTEXT
  ```
- [ ] StatefulSets fully ready:
  ```bash
  kubectl get statefulsets -A --context CLUSTER-CONTEXT
  ```
- [ ] Ingress controllers and load balancers responding
- [ ] Application health checks passing

API and Compatibility Validation
- [ ] No deprecated API warnings in application logs
- [ ] Admission webhooks functioning correctly
- [ ] HPA/VPA behavior unchanged from baseline
- [ ] NetworkPolicies working as expected

Performance & Observability
- [ ] Metrics collection active (no gaps during upgrade)
- [ ] Log aggregation flowing normally
- [ ] Error rates within pre-upgrade baseline
- [ ] API latency (p50/p95/p99) within acceptable range
- [ ] No unexpected 503 errors from API server

Documentation
- [ ] Upgrade completion logged in runbook/changelog
- [ ] Any issues encountered documented for future upgrades
- [ ] Lessons learned shared with team
```

## Key Autopilot Considerations

**Auto-upgrade timing:** Since both prod clusters are on Stable channel, you have ~4 weeks from when 1.32 reaches Regular channel to when it auto-upgrades in Stable. Use your dev clusters on Rapid as early validation.

**Node management:** Skip all node pool upgrade concerns — Autopilot handles this automatically. Your main control point is control plane upgrade timing via maintenance windows/exclusions.

**Resource requests are mandatory:** Any pod without resource requests will be rejected. This is the #1 cause of post-upgrade issues in Autopilot.

**Limited troubleshooting:** No SSH access to nodes. Use `kubectl debug` and Cloud Logging for issue diagnosis.

**Regional availability:** All Autopilot clusters are regional, so control plane stays available during upgrades (unlike zonal clusters).

Would you like me to adjust any timeframes or add specific application validation steps for your workloads?