# GKE Autopilot Upgrade Checklists

**Setup:** 4 Autopilot clusters | Dev: 2 clusters on Rapid | Prod: 2 clusters on Stable | Upgrade: 1.31 → 1.32

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.31 → 1.32
- [ ] Dev Cluster 1: ___ | Prod Cluster 1: ___
- [ ] Dev Cluster 2: ___ | Prod Cluster 2: ___

Compatibility & Version Planning
- [ ] 1.32 available in Stable channel: `gcloud container get-server-config --region REGION --format="yaml(channels.stable)"`
- [ ] Dev clusters already on 1.32+ (should auto-upgrade first on Rapid)
- [ ] No deprecated API usage in prod workloads (check GKE deprecation insights dashboard)
- [ ] GKE 1.32 release notes reviewed for breaking changes from 1.31
- [ ] Third-party operators/controllers tested on dev clusters running 1.32
- [ ] Admission webhooks validated against 1.32 (test on dev first)

Autopilot-Specific Workload Readiness
- [ ] All containers have resource requests (mandatory - missing requests = pod rejection)
- [ ] No privileged containers or host network pods (not supported in Autopilot)
- [ ] terminationGracePeriodSeconds reasonable for graceful shutdown (≤600s recommended)
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Database/stateful workload health verified on dev clusters post-upgrade

Control Plane Timing (Primary Autopilot Control)
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Maintenance exclusion strategy chosen if needed:
      - "No minor or node upgrades" (up to EoS, allows security patches - recommended)
      - "No minor upgrades" (allows patches + node changes)  
      - "No upgrades" (30-day max, emergency use only)
- [ ] Scheduled upgrade notifications enabled (72h advance notice via Cloud Logging)
- [ ] Auto-upgrade target confirmed: `gcloud container clusters get-upgrade-info CLUSTER --region REGION`

Observability & Operations
- [ ] Monitoring baseline captured for both prod clusters (error rates, latency, throughput)
- [ ] Cloud Logging and monitoring active
- [ ] Alerting rules updated for any new 1.32 metrics/labels
- [ ] Upgrade timing communicated to stakeholders
- [ ] On-call team aware of upgrade window
- [ ] Rollback plan documented (control plane patches can be downgraded; minor versions need support)

Dev Environment Validation (Test First Strategy)
- [ ] Both dev clusters upgraded to 1.32 successfully
- [ ] All application functionality verified on dev 1.32 clusters
- [ ] Performance regression testing completed on dev
- [ ] CI/CD pipelines working with 1.32 clusters
- [ ] Soak time completed on dev (minimum 1 week recommended)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot 1.31 → 1.32

Control Plane Health (Per Cluster)
- [ ] Prod Cluster 1 at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] Prod Cluster 2 at 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] System pods healthy both clusters: `kubectl get pods -n kube-system`
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces`
- [ ] Autopilot system components running (GKE manages nodes automatically)

Workload Health Validation
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or ImagePullBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] All PVCs bound: `kubectl get pvc -A`
- [ ] Ingress/load balancers responding (test external endpoints)
- [ ] Application smoke tests passing on both prod clusters

Resource Requests Validation (Autopilot Critical)
- [ ] No pods rejected for missing resource requests
- [ ] Check for any new "Insufficient resources" events: `kubectl get events -A --field-selector reason=FailedScheduling`
- [ ] Resource utilization within expected ranges
- [ ] Autopilot scaling behavior normal (pods scheduling successfully)

Observability Post-Upgrade
- [ ] Metrics pipeline active on both clusters, no collection gaps
- [ ] Cloud Logging flowing normally
- [ ] Error rates within pre-upgrade baseline (compare to dev cluster metrics)
- [ ] Latency (p50/p95/p99) within acceptable range
- [ ] Custom metrics and dashboards displaying correctly
- [ ] Alerting rules firing appropriately (no false positives from version change)

Documentation & Cleanup
- [ ] Upgrade completion documented in changelog
- [ ] Any temporary maintenance exclusions removed
- [ ] Lessons learned captured (especially any Autopilot-specific issues)
- [ ] Team notified of successful upgrade
- [ ] Next upgrade timeline reviewed (Stable channel typically upgrades 4-8 weeks after Rapid)
```

## Key Autopilot Considerations

**Simplified Upgrade Model:** Since Autopilot manages nodes automatically, your main control is over **control plane timing**. Use maintenance windows and exclusions to control when the 1.31→1.32 upgrade happens.

**Resource Requests Critical:** The #1 Autopilot upgrade failure is pods rejected for missing resource requests. This becomes strictly enforced after upgrade.

**Dev-First Validation:** Your Rapid channel dev clusters should upgrade to 1.32 first - use this as your testing ground before prod gets the auto-upgrade.

**No Node Pool Management:** Skip all Standard cluster concerns (surge settings, node strategies, etc.) - GKE handles the underlying infrastructure automatically.

Would you like me to create a specific maintenance window configuration or exclusion strategy for your prod clusters?