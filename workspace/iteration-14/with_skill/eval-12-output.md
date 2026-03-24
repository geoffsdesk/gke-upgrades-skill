# Istio + GKE 1.32 Upgrade Plan

## Executive Summary

**Key insight:** Istio is **very sensitive** to Kubernetes API changes and node restarts. The horror stories are real — mesh upgrades can break ingress, break inter-service communication, or cause cascading pod restarts. Success requires careful sequencing and extensive validation at each step.

**Recommended approach:** Control plane first → Istio compatibility validation → gradual node pool upgrades with surge protection.

## Environment Context
- **Cluster mode:** Standard GKE
- **Current version:** 1.31 → **Target:** 1.32
- **Workload type:** Service mesh (Istio)
- **Risk level:** HIGH (mesh networking + API changes)

## Critical Order of Operations

### Phase 1: Pre-upgrade Istio Assessment

```bash
# Check current Istio version
istioctl version

# Verify Istio 1.32 compatibility
# Istio supports N, N-1 Kubernetes versions
# Check: https://istio.io/latest/docs/releases/supported-releases/

# Backup Istio configuration
kubectl get istio-system -o yaml > istio-backup-$(date +%Y%m%d).yaml
kubectl get gateway,virtualservice,destinationrule -A -o yaml > mesh-config-backup-$(date +%Y%m%d).yaml

# Check for deprecated APIs in Istio objects
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated | grep istio
```

**Stop here if:** Current Istio version doesn't support Kubernetes 1.32. Upgrade Istio first, then return to this plan.

### Phase 2: GKE Control Plane Upgrade

```bash
# Upgrade control plane ONLY (not nodes yet)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.LATEST

# Monitor Istio control plane health during CP upgrade
kubectl get pods -n istio-system -w
istioctl proxy-status  # Should show all proxies connected

# Test basic mesh functionality
kubectl exec -n NAMESPACE POD_NAME -- curl -v http://SERVICE.NAMESPACE.svc.cluster.local
```

**Validation checkpoint:** All Istio system pods Running, proxy-status shows connected sidecars, basic service-to-service calls work.

### Phase 3: Istio Version Compatibility Check

If your Istio version predates 1.32 support, upgrade Istio now (before node upgrades):

```bash
# Download compatible Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.x.x sh -

# In-place upgrade (preserves existing config)
istioctl upgrade --set revision=1-x-x

# Verify mesh health post-Istio upgrade
istioctl proxy-status
kubectl get pods -n istio-system
```

### Phase 4: Node Pool Upgrade Strategy

**Critical for Istio:** Use **conservative surge settings**. Istio sidecars take 30-60 seconds to become ready, and aggressive node replacement can break the mesh connectivity.

```bash
# Set conservative surge for ALL node pools
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade one node pool at a time
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.LATEST
```

**Why conservative?** Istio sidecars need time to:
1. Download new proxy images (if image changed)
2. Establish connections to istiod
3. Receive xDS configuration
4. Pass readiness checks

Aggressive node replacement can create "split brain" scenarios where new sidecars can't reach old istiod or vice versa.

## Istio-Specific Monitoring During Upgrade

### Continuous Health Checks
Run these in separate terminals throughout the upgrade:

```bash
# Terminal 1: Watch Istio system pods
kubectl get pods -n istio-system -w

# Terminal 2: Monitor proxy connectivity
watch 'istioctl proxy-status | head -20'

# Terminal 3: Service mesh connectivity test
watch 'kubectl exec -n NAMESPACE TEST_POD -- curl -s -o /dev/null -w "%{http_code}" http://SERVICE.NAMESPACE.svc.cluster.local'

# Terminal 4: Envoy admin interface health
kubectl port-forward -n NAMESPACE POD_NAME 15000:15000
# Visit http://localhost:15000/ready
```

### Key Istio Failure Indicators
- **Proxy status shows "STALE"** → Sidecar can't reach istiod
- **503 errors between services** → Envoy config issues
- **Connection refused** → Target pod's sidecar not ready
- **Ingress gateway pods CrashLoopBackOff** → Gateway config incompatible

## Common Istio + GKE 1.32 Gotchas

### 1. Gateway API Changes (if using)
GKE 1.32 updates Gateway API CRDs. If you use Istio's Gateway API integration:
```bash
# Check for Gateway API usage
kubectl get gateway -A
kubectl get httproute -A

# Gateway API v1.1+ behavior changes may break existing routes
# Test ingress after control plane upgrade
curl -v https://YOUR_INGRESS_DOMAIN/health
```

### 2. CNI Plugin Changes
```bash
# Check if using Istio CNI plugin
kubectl get daemonset istio-cni-node -n istio-system

# CNI plugins are sensitive to node OS changes
# Monitor pod networking after node replacement
kubectl get events -A --field-selector reason=FailedCreatePodSandBox
```

### 3. Webhook Certificate Issues
Istio's admission webhooks may break with K8s API changes:
```bash
# Check webhook health
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio

# Common fix: restart istiod to refresh certs
kubectl rollout restart deployment/istiod -n istio-system
```

### 4. Sidecar Resource Limits
New node images may have different resource accounting:
```bash
# Check for resource-constrained sidecars
kubectl top pods -A | grep istio-proxy
kubectl describe pods -A | grep -A 10 istio-proxy | grep -E "requests|limits"
```

## Pre-Upgrade Checklist (Istio-Specific)

```markdown
Istio + GKE Compatibility
- [ ] Current Istio version supports Kubernetes 1.32
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] All proxies connected: `istioctl proxy-status`
- [ ] Service mesh traffic flowing: test critical service-to-service calls
- [ ] Istio configuration backed up (gateways, virtual services, destination rules)
- [ ] No deprecated APIs in use: check Istio CRDs and networking objects

Upgrade Strategy
- [ ] Conservative surge settings: maxSurge=1, maxUnavailable=0
- [ ] Node pool upgrade order planned (start with least critical workloads)
- [ ] Rollback plan: can recreate node pools at 1.31 if needed
- [ ] Extended maintenance window: plan 4-6 hours for full cluster

Monitoring
- [ ] Service mesh SLIs baseline captured (success rate, latency)
- [ ] Ingress health check endpoints identified
- [ ] Team has `istioctl` and kubectl access during upgrade
- [ ] PagerDuty/alerting configured for mesh connectivity failures
```

## Post-Upgrade Validation

```bash
# Istio control plane health
kubectl get pods -n istio-system
istioctl version --remote=false  # Control plane version
istioctl proxy-status            # All proxies connected

# Mesh functionality
kubectl exec -n NAMESPACE POD_NAME -- curl -v http://SERVICE.NAMESPACE.svc.cluster.local
kubectl exec -n NAMESPACE POD_NAME -- curl -v https://httpbin.org/get  # External traffic

# Ingress (if applicable)
curl -v https://YOUR_DOMAIN/api/health
curl -I https://YOUR_DOMAIN  # Should not return 503

# Configuration sync
istioctl proxy-config cluster POD_NAME.NAMESPACE | head -10
istioctl proxy-config listener POD_NAME.NAMESPACE | head -10

# Performance validation
# Compare pre/post upgrade: request success rate, p95 latency
```

## Emergency Rollback Plan

If the mesh breaks during node upgrades:

```bash
# Stop the upgrade
gcloud container operations list --cluster CLUSTER_NAME --zone ZONE
# Cancel if possible, or let current node batch finish

# Quick mesh recovery options:
# 1. Restart Istio control plane
kubectl rollout restart deployment/istiod -n istio-system

# 2. Recreate problematic node pool at 1.31
gcloud container node-pools create POOL_NAME-rollback \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.x-gke.LATEST \
  --num-nodes NUM_NODES

# 3. Drain and migrate workloads back
kubectl cordon -l cloud.google.com/gke-nodepool=ORIGINAL_POOL
kubectl drain NODE_NAME --grace-period=300 --ignore-daemonsets
```

## Timeline Expectations

- **Control plane upgrade:** 15-20 minutes
- **Istio compatibility validation:** 30 minutes
- **Per node pool (10 nodes):** 45-60 minutes (conservative surge)
- **Total upgrade time:** 4-6 hours for typical 3-pool cluster

**Success criteria:** All services responding, no 503 errors, ingress functional, proxy-status shows all sidecars connected.

The key to Istio upgrade success is **patience and gradual progression**. Rush the node upgrades, and you'll join the horror story club.