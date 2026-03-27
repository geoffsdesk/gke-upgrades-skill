# GKE + Istio Service Mesh Upgrade Plan

## Context
- **Current**: GKE 1.31 with Istio service mesh
- **Target**: GKE 1.32
- **Risk**: Service mesh compatibility and webhook failures

The key insight: **Istio control plane must be compatible with BOTH the old and new Kubernetes versions during the transition.** This requires careful sequencing and version validation.

## Upgrade Order (Critical)

### Phase 1: Validate Compatibility
```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Check Istio version compatibility matrix
# Visit: https://istio.io/latest/docs/releases/supported-releases/
```

**Compatibility requirements:**
- Istio must support BOTH GKE 1.31 AND 1.32 during the upgrade window
- If current Istio doesn't support 1.32, upgrade Istio FIRST before GKE

### Phase 2: Istio Control Plane (if needed)
```bash
# Only if current Istio doesn't support GKE 1.32
# Download compatible Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.23.x sh -

# Upgrade control plane (canary recommended)
istioctl upgrade --set values.pilot.env.EXTERNAL_ISTIOD=false

# Verify control plane health
kubectl get pods -n istio-system
istioctl proxy-status
```

### Phase 3: GKE Control Plane
```bash
# Add temporary webhook failure policy (safety net)
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version=1.32.x-gke.xxx

# Verify API server compatibility
kubectl get pods -n istio-system
istioctl proxy-status
```

### Phase 4: Node Pool Upgrades
```bash
# Conservative surge settings for mesh workloads
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade node pools
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version=1.32.x-gke.xxx
```

### Phase 5: Data Plane (Sidecar Upgrades)
```bash
# Restart deployments to get new sidecars
kubectl rollout restart deployment -n NAMESPACE

# Or use Istio's rolling upgrade
istioctl upgrade --set values.global.hub=docker.io/istio --set values.global.tag=1.23.x
```

## Service Mesh-Specific Watchouts

### 1. Admission Webhook Failures (Primary Risk)
**Symptom**: Pods fail to create with "admission webhook rejected the request"

**Root cause**: Istio sidecar injector webhook fails on new API server version

**Prevention**:
```bash
# Before upgrade - add failure policy safety net
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

**Recovery**:
```bash
# If pods can't be created post-upgrade
kubectl delete mutatingwebhookconfigurations istio-sidecar-injector
# Redeploy Istio control plane
```

### 2. Certificate Rotation Issues
**Symptom**: mTLS failures, connection refused between services

**Diagnosis**:
```bash
istioctl proxy-config secret POD_NAME.NAMESPACE
kubectl logs -n istio-system -l app=istiod
```

**Fix**: Restart istiod pods to regenerate certificates:
```bash
kubectl rollout restart deployment/istiod -n istio-system
```

### 3. Envoy Proxy Version Skew
**Symptom**: HTTP 503s, connection resets, proxy configuration errors

**Diagnosis**:
```bash
istioctl proxy-status
istioctl proxy-config cluster WORKLOAD_POD.NAMESPACE
```

**Fix**: Rolling restart of workloads to get compatible sidecars:
```bash
kubectl rollout restart deployment -n production
kubectl rollout restart deployment -n staging
```

### 4. Gateway/VirtualService API Changes
**Symptom**: Ingress traffic failures, routing broken

**Check for deprecated APIs**:
```bash
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
kubectl api-resources | grep networking.istio.io
```

## Monitoring During Upgrade

### Pre-upgrade Baseline
```bash
# Capture current mesh metrics
istioctl proxy-status > pre-upgrade-proxy-status.txt
kubectl get pods -n istio-system -o wide > pre-upgrade-control-plane.txt

# Test service-to-service communication
kubectl exec -n production POD_NAME -c SERVICE_CONTAINER -- curl SERVICE_B.production:8080/health
```

### During Upgrade Monitoring
```bash
# Watch for webhook failures
kubectl get events -A --field-selector reason=FailedCreate,reason=FailedScheduling

# Monitor control plane health
watch 'kubectl get pods -n istio-system'

# Check proxy connectivity
istioctl proxy-status | grep -v SYNCED
```

### Post-upgrade Validation
```bash
# Verify all proxies connected
istioctl proxy-status

# Test ingress traffic
curl -H "Host: myapp.example.com" http://INGRESS_IP/health

# Check service mesh metrics
kubectl exec -n istio-system deployment/istiod -- pilot-discovery request GET /debug/endpointz
```

## Rollback Strategy

If service mesh breaks during upgrade:

### Immediate Mitigation
```bash
# Bypass sidecar injection temporarily
kubectl label namespace production istio-injection-

# Scale critical services to bypass mesh
kubectl scale deployment critical-app --replicas=0
kubectl label deployment critical-app sidecar.istio.io/inject=false
kubectl scale deployment critical-app --replicas=3
```

### Full Rollback (if needed)
```bash
# Node pools can be rolled back by creating new pool at old version
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version=1.31.x-gke.xxx
  
# Migrate workloads back to old nodes
kubectl cordon -l cloud.google.com/gke-nodepool=upgraded-pool
```

## Key Success Factors

1. **Version compatibility verification** - Never assume compatibility; check Istio's support matrix
2. **Webhook failure policies** - Always set `failurePolicy: Ignore` before upgrading
3. **Conservative node pool settings** - Use `maxSurge=1` to minimize blast radius
4. **Separate mesh and GKE upgrades** - If Istio needs upgrading, do it first
5. **Baseline metrics** - Capture service-to-service communication patterns before starting

## Timeline Expectations

- **Istio upgrade (if needed)**: 30-60 minutes
- **GKE control plane**: 10-15 minutes  
- **Node pool upgrade**: 2-4 hours (depends on cluster size)
- **Sidecar rollout**: 30-45 minutes
- **End-to-end validation**: 30 minutes

Total: **4-6 hours** for a typical production cluster with proper validation.

The horror stories usually come from skipping the compatibility check and webhook failure policy setup. Follow this sequence and you'll have a smooth upgrade.