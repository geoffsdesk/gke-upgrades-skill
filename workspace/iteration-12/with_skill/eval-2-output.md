# GKE Autopilot Upgrade Checklists
**Environment:** 4 Autopilot clusters | Dev: 2 clusters on Rapid | Prod: 2 clusters on Stable  
**Upgrade:** 1.31 → 1.32 (minor version upgrade)

## Pre-Upgrade Checklist

```markdown
Pre-Upgrade Checklist - Autopilot Clusters
- [ ] Clusters: [Fill in your cluster names] | Mode: Autopilot | Channels: Dev=Rapid, Prod=Stable
- [ ] Current version: 1.31.x | Target version: 1.32.x

Compatibility & Breaking Changes
- [ ] Target version 1.32 available in Stable channel (`gcloud container get-server-config --region REGION --format="yaml(channels)"`)
- [ ] No deprecated API usage - check GKE deprecation insights in Cloud Console
- [ ] Kubernetes 1.32 release notes reviewed for breaking changes (https://kubernetes.io/docs/setup/release/notes/)
- [ ] GKE 1.32 release notes reviewed (https://cloud.google.com/kubernetes-engine/docs/release-notes)
- [ ] Third-party operators/controllers tested against K8s 1.32 (Istio, Argo, etc.)
- [ ] CI/CD pipelines tested against dev clusters already on 1.32 (via Rapid channel)

Workload Readiness (Critical for Autopilot)
- [ ] ALL containers have resource requests set (CPU/memory) - mandatory in Autopilot
- [ ] Resource requests are realistic (not placeholder values like 1m CPU)
- [ ] PodDisruptionBudgets configured for critical workloads (not overly restrictive - allow at least 1 disruption)
- [ ] No bare pods - all workloads managed by Deployments/StatefulSets/Jobs
- [ ] terminationGracePeriodSeconds adequate for graceful shutdown (default 30s usually sufficient)
- [ ] StatefulSet workloads: PV backups completed, reclaim policies verified
- [ ] Database operators (CloudSQL Proxy, etc.): version compatibility confirmed with K8s 1.32

Control Plane Timing (Main lever in Autopilot)
- [ ] Maintenance windows configured for prod clusters (off-peak hours)
- [ ] Consider maintenance exclusion for prod if needed:
      - "No minor upgrades" - blocks 1.31→1.32, allows patches (up to EoS)
      - "No upgrades" - blocks everything for 30 days max (use sparingly)
- [ ] Dev clusters: allow auto-upgrade to proceed first for validation
- [ ] Understand that node upgrades are automatic in Autopilot (Google-managed)

Multi-Cluster Coordination
- [ ] Plan to validate dev clusters first (Rapid channel gives you ~2-4 weeks head start)
- [ ] Smoke test critical workloads on dev after auto-upgrade
- [ ] Document any issues found in dev for prod remediation
- [ ] Stagger prod cluster upgrades if possible (upgrade one, validate, then the other)

Ops Readiness
- [ ] Monitoring active (Cloud Monitoring dashboards for GKE workloads)
- [ ] Baseline metrics captured (error rates, latency, pod restart rates)
- [ ] Upgrade timeline communicated to stakeholders
- [ ] Rollback plan: control plane patch downgrades possible, minor version rollback requires GKE support
- [ ] On-call team aware of upgrade schedule
- [ ] Cloud Logging configured to capture upgrade events and pod failures
```

## Post-Upgrade Checklist

```markdown
Post-Upgrade Checklist - Autopilot Clusters

Control Plane Health
- [ ] Prod cluster 1 at 1.32.x: `gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"`
- [ ] Prod cluster 2 at 1.32.x: `gcloud container clusters describe CLUSTER_NAME --region REGION --format="value(currentMasterVersion)"`
- [ ] System pods healthy in both clusters: `kubectl get pods -n kube-system`
- [ ] GKE system components updated: `kubectl get pods -n gke-system`
- [ ] No control plane error logs in Cloud Logging

Node Health (Google-managed in Autopilot)
- [ ] All nodes show Ready status: `kubectl get nodes`
- [ ] Node versions automatically updated (Autopilot manages this)
- [ ] No node-level events indicating problems: `kubectl get events -A --field-selector type=Warning`

Workload Health - Cluster 1
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Jobs completing successfully: `kubectl get jobs -A`
- [ ] No resource quota violations: `kubectl get events -A --field-selector reason=FailedCreate`

Workload Health - Cluster 2
- [ ] All deployments at desired replica count: `kubectl get deployments -A`
- [ ] No CrashLoopBackOff or Pending pods: `kubectl get pods -A --field-selector=status.phase!=Running,status.phase!=Succeeded`
- [ ] StatefulSets fully ready: `kubectl get statefulsets -A`
- [ ] Jobs completing successfully: `kubectl get jobs -A`
- [ ] No resource quota violations: `kubectl get events -A --field-selector reason=FailedCreate`

Application Validation
- [ ] Load balancers and Ingress controllers responding
- [ ] External traffic reaching applications (test key endpoints)
- [ ] Internal service-to-service communication working
- [ ] Database connections healthy (CloudSQL, external DBs)
- [ ] Application health checks passing
- [ ] Critical user journeys smoke tested

Observability & Performance
- [ ] Metrics pipeline active, no collection gaps in Cloud Monitoring
- [ ] Application logs flowing normally to Cloud Logging
- [ ] Error rates within pre-upgrade baseline
- [ ] Response latency (p50/p95/p99) within acceptable range
- [ ] No new error patterns in logs
- [ ] Resource consumption normal (CPU/memory usage patterns)

Cleanup & Documentation
- [ ] Any temporary maintenance exclusions removed
- [ ] Upgrade documented in change management system
- [ ] Issues/lessons learned captured for next upgrade cycle
- [ ] Dev team notified that prod is now on 1.32 (version alignment)
- [ ] Update internal documentation if any new K8s 1.32 features adopted
```

## Key Autopilot Considerations

**What's Different in Autopilot:**
- ✅ **Simplified:** No node pool management, surge settings, or blue-green strategies needed
- ✅ **Automatic:** Google handles node upgrades completely
- ⚠️ **Resource requests mandatory:** Missing CPU/memory requests cause pod rejection
- ⚠️ **Limited control:** Main levers are maintenance windows and exclusions for control plane timing

**Recommended Approach:**
1. Let dev clusters (Rapid channel) upgrade first automatically
2. Validate workloads on dev clusters running 1.32
3. Allow prod clusters (Stable channel) to auto-upgrade ~2-4 weeks later
4. Use maintenance windows to control timing within your preferred hours
5. Only use maintenance exclusions if you need to delay beyond the automatic schedule

**Troubleshooting Note:** In Autopilot, you can't SSH to nodes for debugging. Use `kubectl debug` for pod-level issues and Cloud Logging for system-level events.