# GKE Autopilot Upgrade Checklists

**Environment:** 4 Autopilot clusters (2 dev/Rapid, 2 prod/Stable)  
**Upgrade:** 1.31 → 1.32 (auto-upgrade next month)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Dev clusters: ___ & ___ | Prod clusters: ___ & ___
- [ ] All clusters: Autopilot mode | Dev: Rapid channel | Prod: Stable channel

Compatibility & Breaking Changes
- [ ] GKE 1.32 release notes reviewed for Autopilot-specific changes
- [ ] No deprecated API usage in any cluster (check GKE deprecation insights dashboard)
- [ ] Kubernetes 1.32 upstream changelog reviewed for breaking changes
- [ ] Verify all workloads have resource requests (mandatory for Autopilot)
- [ ] Third-party controllers/operators support Kubernetes 1.32

Dev Environment Validation (Will upgrade first on Rapid)
- [ ] Dev clusters already at 1.32? Check: `gcloud container clusters describe DEV_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"`
- [ ] If dev at 1.32: workload health validated, any issues documented
- [ ] If dev not yet upgraded: monitoring active to capture upgrade behavior

Workload Readiness (All Clusters)
- [ ] PDBs configured for critical services (not overly restrictive - allow some disruption)
- [ ] No bare pods - all workloads managed by Deployments/StatefulSets/Jobs
- [ ] Resource requests set on ALL containers (CPU/memory - Autopilot requirement)
- [ ] terminationGracePeriodSeconds ≤ 600s (10min max for Autopilot, 25s for Spot)
- [ ] StatefulSet data backed up (application-level snapshots taken)
- [ ] Admission webhooks tested against K8s 1.32 (cert-manager, policy controllers, etc.)

Production Timing Control
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] If delaying prod upgrade: "no upgrades" exclusion applied (30-day max):
      `gcloud container clusters update PROD_CLUSTER --region REGION --add-maintenance-exclusion-name="defer-132" --add-maintenance-exclusion-start=START --add-maintenance-exclusion-end=END --add-maintenance-exclusion-scope=no_upgrades`
- [ ] Stakeholders notified of upgrade window
- [ ] On-call team aware and available during maintenance window

Observability & Rollback Readiness
- [ ] Baseline metrics captured (error rates, latency, resource usage)
- [ ] Cloud Monitoring alerts active
- [ ] Application health check endpoints verified
- [ ] Rollback plan documented (limited options for Autopilot - mainly application-level)
- [ ] Understanding: Autopilot nodes managed by Google, no SSH access for debugging
```

## Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Control Plane Health (All Clusters)
- [ ] Dev Cluster 1 at 1.32: `gcloud container clusters describe DEV_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"`
- [ ] Dev Cluster 2 at 1.32: `gcloud container clusters describe DEV_CLUSTER_2 --region REGION --format="value(currentMasterVersion)"`  
- [ ] Prod Cluster 1 at 1.32: `gcloud container clusters describe PROD_CLUSTER_1 --region REGION --format="value(currentMasterVersion)"`
- [ ] Prod Cluster 2 at 1.32: `gcloud container clusters describe PROD_CLUSTER_2 --region REGION --format="value(currentMasterVersion)"`
- [ ] All nodes Ready: `kubectl get nodes` (across all clusters)
- [ ] System pods healthy: `kubectl get pods -n kube-system` (check each cluster)

Workload Health Validation
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No failing pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Jobs completed successfully: `kubectl get jobs -A`
- [ ] Ingress controllers responding (test load balancer endpoints)
- [ ] Application smoke tests passing

Autopilot-Specific Checks
- [ ] Pod scheduling working normally (no resource request violations)
- [ ] Autopilot node scaling responding to demand
- [ ] No resource constraint errors in pod events
- [ ] Verify workloads not hitting new Autopilot resource limits in 1.32

Cross-Cluster Validation
- [ ] Dev clusters stable after 1.32 upgrade
- [ ] Production traffic routing normally
- [ ] Inter-cluster communication working (if applicable)
- [ ] DNS resolution across all clusters

Observability Post-Upgrade
- [ ] Metrics pipeline active across all clusters
- [ ] Cloud Logging flowing normally
- [ ] Error rates within baseline (compare to pre-upgrade metrics)
- [ ] API latency within expected range
- [ ] Resource utilization patterns normal

Documentation & Communication
- [ ] Remove temporary maintenance exclusions (if applied)
- [ ] Upgrade completion documented in runbook/changelog
- [ ] Team notified of successful upgrade
- [ ] Any issues encountered documented for future upgrades
- [ ] Lessons learned: note any Autopilot-specific behavior changes in 1.32
```

## Key Autopilot Considerations

**Upgrade Flow:** Your dev clusters on Rapid channel will upgrade to 1.32 first (within ~2 weeks of upstream K8s 1.32 release). Your prod clusters on Stable will upgrade ~2-4 weeks later. Use the dev upgrade as validation.

**Limited Control:** Autopilot gives you less upgrade control than Standard - you can only control **when** via maintenance windows and exclusions, not **how** (node strategies are managed by Google).

**Auto-validation Strategy:** 
1. Let dev clusters upgrade automatically on Rapid
2. Monitor dev cluster health for 1-2 weeks  
3. If issues found, apply "no upgrades" exclusion to prod clusters while you fix
4. If dev stable, let prod clusters auto-upgrade during their maintenance windows

**Troubleshooting:** With no SSH access, use `kubectl logs`, `kubectl describe`, and `kubectl debug` for pod-level issues. Check Cloud Logging for node-level events.

Would you like me to create a monitoring runbook for tracking the dev cluster upgrades, or help you set up the maintenance windows for your prod clusters?