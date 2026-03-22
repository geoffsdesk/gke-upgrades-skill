# GKE Autopilot Upgrade Checklists

## Environment Summary
- **4 Autopilot clusters**: 2 dev (Rapid), 2 prod (Stable)
- **Upgrade**: 1.31 → 1.32 auto-upgrade for prod clusters
- **Timeline**: Next month

## Pre-Upgrade Checklist - Production Clusters (1.31 → 1.32)

```markdown
Pre-Upgrade Checklist - Autopilot Production
- [ ] Cluster 1: ___ | Cluster 2: ___ | Mode: Autopilot | Channel: Stable
- [ ] Current version: 1.31 | Target version: 1.32

Compatibility & Testing
- [ ] Dev clusters already on 1.32+ via Rapid channel - validate workloads there first
- [ ] Target version (1.32) confirmed available in Stable channel: `gcloud container get-server-config --region REGION --format="yaml(channels.stable)"`
- [ ] No deprecated API usage (check GKE deprecation insights dashboard in Cloud Console)
- [ ] GKE 1.32 release notes reviewed for breaking changes: https://cloud.google.com/kubernetes-engine/docs/release-notes
- [ ] Third-party operators/controllers tested on dev clusters (1.32+) and confirmed compatible
- [ ] Admission webhooks tested against 1.32 on dev environment

Workload Readiness (Autopilot Requirements)
- [ ] ALL containers have resource requests set (mandatory for Autopilot)
- [ ] ALL containers have resource limits set (strongly recommended)
- [ ] PDBs configured for critical workloads (not overly restrictive - allow at least 1 disruption)
- [ ] No bare pods — all workloads managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown (default 30s usually sufficient)
- [ ] StatefulSet data backed up, PV reclaim policies verified
- [ ] Database/stateful workload compatibility verified on dev clusters

Auto-Upgrade Controls
- [ ] Maintenance windows configured for off-peak hours: `gcloud container clusters describe CLUSTER --region REGION --format="value(maintenancePolicy)"`
- [ ] Consider maintenance exclusion if timing is critical:
      - "No upgrades" (30-day max, blocks everything) - use for code freezes
      - "No minor or node upgrades" (up to EoS, allows CP patches) - max control
      - "No minor upgrades" (up to EoS, allows patches + node upgrades)
- [ ] Auto-upgrade target confirmed: `gcloud container clusters get-upgrade-info CLUSTER --region REGION`
- [ ] Scheduled upgrade notifications enabled (72h advance notice via Cloud Logging)

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring dashboards, alerts configured)
- [ ] Baseline metrics captured: error rates, latency, throughput, pod restart rates
- [ ] Upgrade timing communicated to stakeholders and customers
- [ ] On-call team aware and available during maintenance window
- [ ] Rollback plan documented (control plane patches can be downgraded; minor versions require support)
- [ ] Dev clusters serve as canary validation - any issues observed there?
```

## Post-Upgrade Checklist - Production Clusters

```markdown
Post-Upgrade Checklist - Autopilot Production

Cluster Health
- [ ] Control plane at version 1.32: `gcloud container clusters describe CLUSTER --region REGION --format="value(currentMasterVersion)"`
- [ ] Autopilot node management active: `kubectl get nodes` (all should show Ready)
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] GKE managed services operational: `kubectl get pods -n gke-system`
- [ ] No stuck PDBs blocking operations: `kubectl get pdb --all-namespaces`

Workload Health  
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or ImagePullBackOff pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready with all replicas: `kubectl get statefulsets -A`
- [ ] Jobs completed successfully: `kubectl get jobs -A`
- [ ] Ingress controllers responding: `kubectl get ingress -A`
- [ ] LoadBalancer services have external IPs: `kubectl get services -A --field-selector=spec.type=LoadBalancer`

Application Validation
- [ ] Application health checks passing
- [ ] Smoke tests executed successfully
- [ ] Database connections working (if applicable)
- [ ] External API integrations functional
- [ ] User-facing services responding normally

Observability & Performance
- [ ] Cloud Monitoring metrics flowing (no collection gaps)
- [ ] Cloud Logging ingestion active
- [ ] Error rates within pre-upgrade baseline
- [ ] Response latency (p50/p95/p99) within acceptable range
- [ ] Resource utilization normal (CPU/memory)
- [ ] No new alerts or anomalies

Cleanup & Documentation
- [ ] Autopilot automatically manages node lifecycle - no manual cleanup needed
- [ ] Upgrade documented in change log with version numbers and timing
- [ ] Any issues encountered documented for future reference
- [ ] Dev environment alignment confirmed (both environments on compatible versions)
```

## Key Autopilot Considerations

**Simplified Upgrade Process**: Since you're on Autopilot, Google manages the node upgrades automatically. Your primary control is over **when** the control plane upgrades happen (via maintenance windows/exclusions).

**Resource Requests are Critical**: The #1 cause of Autopilot upgrade failures is missing resource requests. Every container must have CPU and memory requests defined.

**Dev-First Validation**: Since your dev clusters are on Rapid channel, they'll get 1.32 first. Use them as your testing ground before prod auto-upgrades.

**Timing Control**: If you need to delay the upgrade, apply a maintenance exclusion before the auto-upgrade window. The "no minor upgrades" exclusion will block the 1.31→1.32 upgrade while still allowing security patches.

Would you like me to create specific gcloud commands for configuring maintenance windows or exclusions for your clusters?