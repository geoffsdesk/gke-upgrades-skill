# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful coordination between the GKE control plane, Istio control plane, and data plane components. Here's a safe upgrade sequence.

## Pre-flight Validation

**Critical compatibility check:**
```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Verify Istio 1.31/1.32 compatibility matrix
# Istio follows K8s N-2 support policy - check https://istio.io/latest/docs/releases/supported-releases/
```

**Istio-specific pre-checks:**
```bash
# Mesh health baseline
istioctl proxy-status
istioctl analyze -A

# Sidecar injection status
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.annotations.sidecar\.istio\.io/status}{"\n"}{end}' | grep -v "null"

# Certificate expiry (if using Istio CA)
kubectl get secrets -n istio-system -l istio.io/key-type=self-signed-root -o jsonpath='{.items[0].data.cert-chain\.pem}' | base64 -d | openssl x509 -text | grep "Not After"
```

## Recommended Upgrade Sequence

### Phase 1: Istio Control Plane First (if needed)

**Important:** Only upgrade Istio if your current version doesn't support K8s 1.32. Many Istio versions support multiple K8s versions.

If Istio upgrade is needed:
```bash
# Download compatible Istio version
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.XX.X sh -

# Canary upgrade (recommended)
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=true --revision=1-XX-X

# Gradually migrate workloads to new revision
kubectl label namespace NAMESPACE istio-injection- istio.io/rev=1-XX-X

# Validate mesh connectivity after each namespace migration
```

### Phase 2: GKE Control Plane Upgrade

```bash
# Add temporary maintenance exclusion to prevent auto node upgrades during mesh validation
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --add-maintenance-exclusion-name "istio-upgrade-freeze" \
  --add-maintenance-exclusion-start-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-end-time "$(date -u -d '+7 days' +%Y-%m-%dT%H:%M:%SZ)" \
  --add-maintenance-exclusion-scope no_minor_or_node_upgrades

# Upgrade control plane only
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.X-gke.XXXX
```

**Critical validation after CP upgrade:**
```bash
# Verify Istio control plane still functional
kubectl get pods -n istio-system
istioctl proxy-status | grep -v SYNCED  # Should be empty

# Test mesh connectivity
kubectl exec -it POD_NAME -c CONTAINER_NAME -- curl -s SERVICE_NAME.NAMESPACE.svc.cluster.local
```

### Phase 3: Node Pool Upgrades (Conservative Strategy)

Use **surge upgrade with conservative settings** for mesh workloads:

```bash
# Configure conservative surge settings
gcloud container node-pools update NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade one pool at a time
gcloud container node-pools upgrade NODE_POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.X-gke.XXXX
```

**Why conservative settings for mesh:**
- Istio sidecars need time to establish mTLS connections to new Envoy instances
- Service discovery updates propagate through the mesh gradually
- Higher surge rates can cause traffic routing instability

## Mesh-Specific Monitoring During Upgrade

**Watch for these Istio failure patterns:**

```bash
# Monitor sidecar injection on new nodes
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.spec.nodeName}{"\t"}{.metadata.annotations.sidecar\.istio\.io/status}{"\n"}{end}' | grep NODE_NAME

# Certificate propagation issues
kubectl logs -n istio-system -l app=istiod | grep -i "certificate\|tls\|failed"

# Envoy configuration sync
istioctl proxy-status | grep -E "STALE|NOT SENT"

# Service mesh error rates (if using Prometheus/Grafana)
# Query: rate(istio_requests_total{response_code!~"2.*"}[5m])
```

## Common Mesh Upgrade Gotchas

### 1. Admission Webhook Certificate Issues
**Symptom:** Pods fail to create with "admission webhook rejected" after CP upgrade

**Immediate fix:**
```bash
# Temporarily set webhook failure policy to Ignore
kubectl patch validatingwebhookconfigurations istio-validator-istio-system \
  -p '{"webhooks":[{"name":"validation.istio.io","failurePolicy":"Ignore"}]}'

# Or restart Istio to regenerate certificates
kubectl rollout restart deployment/istiod -n istio-system
```

### 2. Sidecar Injection Version Mismatch
**Symptom:** New pods get wrong Istio version injected

**Fix:** Verify injection webhook points to correct Istio revision:
```bash
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml | grep "revision\|name"
```

### 3. Cross-Node mTLS Failures
**Symptom:** Intermittent 503s during node upgrades

**Cause:** New Envoy sidecars take time to sync certificates and service discovery

**Mitigation:** Use circuit breakers and retry policies:
```yaml
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: circuit-breaker
spec:
  host: SERVICE_NAME
  trafficPolicy:
    outlierDetection:
      consecutiveErrors: 3
      interval: 30s
      baseEjectionTime: 30s
```

### 4. CNI Plugin Compatibility
**Symptom:** Pods stuck in Init state on new nodes

**Check:** Verify Istio CNI compatibility with new node image:
```bash
kubectl describe pod POD_NAME | grep -A 10 "Init Containers"
kubectl logs POD_NAME -c istio-init
```

## Validation Checklist

```markdown
Istio + GKE Upgrade Validation
- [ ] Control plane at 1.32: `gcloud container clusters describe CLUSTER --format="value(currentMasterVersion)"`
- [ ] All nodes at 1.32: `kubectl get nodes -o wide`
- [ ] Istio control plane healthy: `kubectl get pods -n istio-system`
- [ ] No stale proxy configurations: `istioctl proxy-status`
- [ ] Sidecar injection working: Deploy test pod and verify injection
- [ ] Cross-service connectivity: `kubectl exec POD -- curl SERVICE.NAMESPACE.svc.cluster.local`
- [ ] mTLS certificates valid: Check certificate expiry dates
- [ ] Service mesh metrics flowing: Verify Prometheus/Grafana dashboards
- [ ] No 503 spikes in application metrics
- [ ] Admission webhooks functional: `kubectl run test-pod --image=nginx --rm -it --restart=Never`
```

## Emergency Rollback Plan

If mesh breaks after upgrade:

```bash
# 1. Revert Istio to previous revision (if you upgraded Istio)
kubectl label namespace NAMESPACE istio.io/rev- istio-injection=enabled

# 2. Scale down problematic workloads temporarily
kubectl scale deployment DEPLOYMENT_NAME --replicas=0

# 3. Create new node pool at 1.31 and migrate critical workloads
gcloud container node-pools create recovery-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX \
  --num-nodes 3
```

## Timeline Recommendation

- **Day 1:** Istio compatibility validation and control plane upgrade
- **Day 2-3:** Soak period, monitor mesh metrics 
- **Day 4:** Begin node pool upgrades (one pool per day)
- **Day 7:** Remove maintenance exclusion, validate full upgrade

The conservative timeline accounts for mesh propagation delays and gives you time to catch subtle issues before they affect production traffic.