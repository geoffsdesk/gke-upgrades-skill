# Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot Production Clusters
- [ ] Cluster 1: ___ | Mode: Autopilot | Channel: Stable
- [ ] Cluster 2: ___ | Mode: Autopilot | Channel: Stable  
- [ ] Current version: 1.29.x | Target version: 1.30.x

Compatibility
- [ ] Target version 1.30 available in Stable channel (`gcloud container get-server-config --zone ZONE --format="yaml(channels.stable)"`)
- [ ] No deprecated API usage (check GKE deprecation insights dashboard - critical for 1.29→1.30)
- [ ] GKE 1.30 release notes reviewed for breaking changes from 1.29
- [ ] Third-party operators/controllers compatible with K8s 1.30
- [ ] Admission webhooks tested against 1.30 (if any)

Workload Readiness (Autopilot-specific)
- [ ] ALL containers have resource requests defined (mandatory in Autopilot)
- [ ] PDBs configured for critical workloads (not overly restrictive)
- [ ] No bare pods — all managed by Deployments/StatefulSets
- [ ] terminationGracePeriodSeconds reasonable for graceful shutdown
- [ ] StatefulSet PV backups completed, reclaim policies verified
- [ ] Database operators compatible with K8s 1.30 (if applicable)

Infrastructure (Autopilot - simplified)
- [ ] Maintenance window configured for off-peak hours on both prod clusters
- [ ] Consider maintenance exclusion if needed during critical periods:
      - "No minor upgrades" (allows patches, blocks 1.29→1.30 until you're ready)
- [ ] Dev clusters on Rapid already upgraded to 1.30? (validation opportunity)
- [ ] Rollout sequencing configured to stagger the 2 prod clusters

Ops Readiness
- [ ] Cloud Monitoring active, baseline metrics captured
- [ ] Upgrade window communicated to stakeholders
- [ ] On-call team aware (node restarts will occur - managed by Google)
- [ ] Scheduled upgrade notifications enabled (72h advance via Cloud Logging)
- [ ] Consider upgrading dev clusters first as final validation
```

# Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot Production Clusters

Cluster Health
- [ ] Cluster 1 control plane at 1.30.x: `gcloud container clusters describe CLUSTER1 --zone ZONE --format="value(currentMasterVersion)"`
- [ ] Cluster 2 control plane at 1.30.x: `gcloud container clusters describe CLUSTER2 --zone ZONE --format="value(currentMasterVersion)"`
- [ ] All nodes Ready (Google-managed): `kubectl get nodes` 
- [ ] System pods healthy: `kubectl get pods -n kube-system`
- [ ] GKE Autopilot system workloads running: `kubectl get pods -n gke-system`
- [ ] No stuck PDBs: `kubectl get pdb --all-namespaces`

Workload Health (Both Clusters)
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Ingress/Gateway API load balancers responding
- [ ] Application health checks and smoke tests passing

Resource Validation (Autopilot)
- [ ] No pods rejected for missing resource requests
- [ ] Autopilot node provisioning working: `kubectl describe pods` (check scheduling events)
- [ ] Vertical Pod Autoscaling recommendations updated for K8s 1.30

Observability
- [ ] Cloud Monitoring metrics flowing, no collection gaps
- [ ] Cloud Logging capturing application and system logs
- [ ] Error rates within pre-upgrade baseline
- [ ] Latency (p50/p95/p99) within pre-upgrade baseline

Cleanup & Documentation
- [ ] Remove temporary maintenance exclusions (if used)
- [ ] Upgrade documented in changelog
- [ ] Lessons learned captured for next upgrade cycle
- [ ] Consider updating dev clusters to next available version for continued validation
```

## Key Autopilot Considerations

Since you're running Autopilot, the upgrade is much simpler than Standard clusters:

- **No node pool management needed** - Google handles all node lifecycle
- **Resource requests are mandatory** - Any missing requests will cause pod rejection
- **Control plane upgrade happens first** - Node refreshes follow automatically  
- **Use your dev clusters** - Since they're on Rapid channel, they likely already have 1.30 and can serve as validation

The most common issue in Autopilot upgrades is workloads missing resource requests, so double-check that all your pods have proper `requests` defined.