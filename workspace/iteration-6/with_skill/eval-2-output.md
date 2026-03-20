# GKE Autopilot Upgrade Checklists
**Environment:** 4 Autopilot clusters | Dev: Rapid channel | Prod: Stable channel
**Upgrade:** 1.29 → 1.30 (prod clusters auto-upgrading next month)

## Pre-Upgrade Checklist

```
Pre-Upgrade Checklist - Autopilot 1.29 → 1.30
- [ ] Cluster: ___ | Mode: Autopilot | Channel: Stable
- [ ] Current version: 1.29.x | Target version: 1.30.x

Compatibility
- [ ] 1.30 available in Stable channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard)
- [ ] GKE 1.30 release notes reviewed for breaking changes
- [ ] Third-party operators/controllers compatible with K8s 1.30
- [ ] Admission webhooks tested against 1.30 (if any)

Workload Readiness (Autopilot-specific)
- [ ] All containers have resource requests (mandatory - pods will be rejected without them)
- [ ] Resource requests within Autopilot limits (CPU: 0.25-110 cores, Memory: 0.5-420 GiB per container)
- [ ] No privileged containers or host access requirements
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] terminationGracePeriodSeconds reasonable (≤120s recommended)
- [ ] StatefulSet PV backups completed if applicable

Dev Environment Testing
- [ ] Rapid channel dev clusters already running 1.30.x successfully
- [ ] Application smoke tests passed on 1.30 in dev
- [ ] Critical workload behaviors verified on 1.30
- [ ] No regression in application startup times or resource consumption

Release Channel & Timing
- [ ] Both prod clusters on Stable channel confirmed
- [ ] Auto-upgrade notifications received and timing noted
- [ ] Maintenance window configured for off-peak hours (optional - auto-upgrades respect them)
- [ ] Consider "no upgrades" exclusion if critical period conflicts (max 30 days)

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring + application metrics)
- [ ] Baseline metrics captured (error rates, latency, resource usage)
- [ ] Upgrade timing communicated to stakeholders
- [ ] On-call team aware of upgrade schedule
- [ ] Rollback plan documented (create new cluster if needed - CP downgrade not supported)
```

## Post-Upgrade Checklist

```
Post-Upgrade Checklist - Autopilot

Control Plane Health
- [ ] Both prod clusters at 1.30.x: `gcloud container clusters describe CLUSTER --zone ZONE --format="value(currentMasterVersion)"`
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] Autopilot system components running: `kubectl get pods -n gke-system`

Workload Health
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No rejected pods due to missing resource requests: `kubectl get events -A --field-selector reason=FailedCreate`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/load balancers responding
- [ ] Application health checks passing

Resource & Performance
- [ ] Pod resource requests still within Autopilot limits
- [ ] No unexpected resource consumption spikes
- [ ] Application startup times normal
- [ ] Node auto-provisioning working (pods schedule successfully)

Observability
- [ ] Cloud Logging collection active
- [ ] Cloud Monitoring metrics flowing
- [ ] Application metrics pipeline healthy
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within acceptable range

Documentation
- [ ] Upgrade completion documented
- [ ] Any issues or lessons learned captured
- [ ] Team notified of successful completion
```

## Key Autopilot Considerations

**Resource requests are mandatory** - Unlike Standard GKE, Autopilot rejects pods without resource requests. This is the #1 cause of post-upgrade issues.

**No node management** - Google handles all node operations automatically. Your only timing control is the maintenance window and exclusions.

**Debugging changes** - No SSH access to nodes. Use `kubectl debug` and Cloud Logging for troubleshooting.

**Dev → Prod validation** - Since your dev clusters on Rapid channel get 1.30 first, use them to validate your workloads before the Stable channel auto-upgrade hits prod.

**Maintenance exclusions for critical periods** - If the auto-upgrade timing conflicts with a critical business period, apply a "no upgrades" exclusion (up to 30 days) to defer.

Would you like me to also create a runbook with specific `gcloud` commands for monitoring the upgrade progress, or do you need guidance on setting up maintenance windows for the auto-upgrade timing?