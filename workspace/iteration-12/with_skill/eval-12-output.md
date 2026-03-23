# Istio + GKE 1.32 Upgrade Plan

Istio service mesh upgrades alongside GKE require careful sequencing to avoid control plane/data plane version skew and traffic disruption. Here's your battle-tested approach:

## Current Environment Assessment

**Assumptions (please confirm):**
- Standard GKE cluster at 1.31.x
- Istio version: ~1.22-1.23 (typical for GKE 1.31 timeframe)
- Target: GKE 1.32.x
- Release channel: Regular/Stable (fill in: ___)

## Critical Success Factors

1. **Version compatibility matrix** — Istio has strict K8s version requirements
2. **Upgrade sequencing** — Control plane → Istio → Node pools (never reverse this)
3. **Envoy proxy compatibility** — New nodes get new Envoy, old sidecars may be incompatible
4. **mTLS certificate rotation** — Mesh certificates can expire during long upgrades

## Pre-Flight Compatibility Check

```bash
# Check current Istio version
kubectl get pods -n istio-system -l app=istiod -o jsonpath='{.items[0].spec.containers[0].image}'

# Verify Istio control plane health
istioctl proxy-status
istioctl analyze --all-namespaces

# Check for deprecated Istio APIs (common culprit)
kubectl get --raw /metrics | grep apiserver_request_total | grep -E "networking\.istio\.io|security\.istio\.io"
```

**Compatibility verification:**
- Istio 1.22+ supports K8s 1.32
- If you're on Istio <1.22, you MUST upgrade Istio before GKE
- Check [Istio supported releases](https://istio.io/latest/docs/releases/supported-releases/) for your exact versions

## Recommended Upgrade Sequence

### Phase 1: Istio Upgrade (if needed)
**Do this BEFORE touching GKE if you're on Istio <1.22**

```bash
# Canary upgrade method (recommended)
istioctl install --set revision=1-23-0 --set values.pilot.env.EXTERNAL_ISTIOD=false

# Verify canary control plane
kubectl get pods -n istio-system -l app=istiod

# Migrate workloads gradually (test namespace first)
kubectl label namespace NAMESPACE istio.io/rev=1-23-0 --overwrite
kubectl rollout restart deployment -n NAMESPACE

# Validate traffic flow
istioctl proxy-config cluster POD_NAME.NAMESPACE
```

### Phase 2: GKE Control Plane Upgrade
```bash
# Upgrade control plane first (Istio running on old nodes is OK temporarily)
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.x-gke.PATCH

# Critical: Monitor Istio control plane during CP upgrade
kubectl get pods -n istio-system -w
```

### Phase 3: Node Pool Upgrade Strategy
**This is where most mesh upgrades fail.**

**Conservative approach (recommended for production):**
```bash
# Configure conservative surge settings
gcloud container node-pools update POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade one pool at a time
gcloud container node-pools upgrade POOL_NAME \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.PATCH
```

**Alternative: Blue-Green for mesh workloads**
```bash
# Create new pool at target version
gcloud container node-pools create POOL_NAME-132 \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.x-gke.PATCH \
  --num-nodes NUM_NODES

# Migrate mesh workloads namespace by namespace
kubectl cordon -l cloud.google.com/gke-nodepool=POOL_NAME
# Test traffic flow after each namespace migration
```

## Istio-Specific Monitoring During Upgrade

### Critical Health Checks
```bash
# Control plane connectivity
istioctl proxy-status | grep -v SYNCED

# Certificate expiration (mesh upgrades can be slow)
kubectl get secret -n istio-system -o json | \
  jq -r '.items[] | select(.metadata.name | contains("cacerts")) | .data."cert-chain.pem"' | \
  base64 -d | openssl x509 -text -noout | grep "Not After"

# Envoy version skew across nodes
kubectl get pods -A -o json | \
  jq -r '.items[] | select(.spec.containers[]?.image | contains("proxyv2")) | "\(.metadata.namespace)/\(.metadata.name): \(.spec.containers[] | select(.image | contains("proxyv2")).image)"'
```

### Traffic Validation Commands
```bash
# Test service-to-service connectivity
kubectl exec POD_NAME -c CONTAINER_NAME -- curl -s SERVICE_NAME:PORT/health

# Check mTLS is working
istioctl authn tls-check POD_NAME.NAMESPACE SERVICE_NAME.NAMESPACE

# Verify load balancing
for i in {1..10}; do kubectl exec POD_NAME -- curl -s SERVICE_NAME/endpoint | grep hostname; done
```

## Common Istio + GKE Upgrade Failures

### 1. Envoy proxy version skew
**Problem:** New nodes have newer Envoy, old sidecars can't communicate
**Symptoms:** 503 errors, connection refused between services
**Fix:**
```bash
# Force sidecar restart after node upgrade
kubectl rollout restart deployment -n NAMESPACE
# Or delete pods to trigger recreation
kubectl delete pods -l app=APP_NAME -n NAMESPACE
```

### 2. Istio webhook blocking pod creation
**Problem:** ValidatingAdmissionWebhook rejects pods on new nodes
**Symptoms:** Pods stuck Pending with admission errors
**Fix:**
```bash
# Check webhook status
kubectl get validatingwebhookconfigurations istio-validator-istio-system

# Temporarily disable if needed
kubectl patch validatingwebhookconfigurations istio-validator-istio-system \
  -p '{"webhooks":[{"name":"config.validation.istio.io","admissionReviewVersions":["v1","v1beta1"],"failurePolicy":"Ignore"}]}'
```

### 3. Certificate rotation during upgrade
**Problem:** Long upgrades (>24h) hit certificate expiration
**Fix:**
```bash
# Monitor cert expiration
kubectl get secret istio-ca-secret -n istio-system -o json | \
  jq -r '.data."cert-chain.pem"' | base64 -d | openssl x509 -dates -noout

# Force cert rotation if needed
kubectl delete secret cacerts -n istio-system
kubectl rollout restart deployment/istiod -n istio-system
```

### 4. Gateway/Ingress connectivity loss
**Problem:** Istio Gateway pods land on new nodes, external LB health checks fail
**Symptoms:** External traffic 502/503 errors
**Fix:**
```bash
# Check gateway pod distribution
kubectl get pods -n istio-system -l app=istio-proxy -o wide

# Force gateway restart if needed
kubectl rollout restart deployment/istio-proxy -n istio-system
```

## Pre-Upgrade Checklist

```markdown
Istio + GKE 1.32 Upgrade Checklist

Compatibility
- [ ] Current Istio version: _____ (confirm ≥1.22 for K8s 1.32)
- [ ] Istio control plane healthy: `istioctl analyze --all-namespaces`
- [ ] No deprecated Istio APIs in use
- [ ] Mesh certificates >48h from expiration
- [ ] All sidecars injected (no naked pods in mesh namespaces)

Pre-upgrade Testing
- [ ] Baseline traffic metrics captured (error rates, latency P99)
- [ ] Service-to-service connectivity verified
- [ ] External ingress traffic tested
- [ ] mTLS verification passing: `istioctl authn tls-check`
- [ ] Staging environment upgrade completed successfully

Infrastructure
- [ ] Conservative surge settings: maxSurge=1, maxUnavailable=0
- [ ] Sufficient quota for surge nodes
- [ ] PDBs configured but not overly restrictive
- [ ] Monitoring/alerting active on mesh metrics
- [ ] Rollback plan documented (includes Istio rollback)
```

## Post-Upgrade Validation

```bash
# Mesh health comprehensive check
istioctl proxy-status
istioctl analyze --all-namespaces

# Traffic flow validation
# Test each service pair in your mesh
kubectl exec POD_A -- curl -s SERVICE_B:PORT/health

# Certificate validation
istioctl authn tls-check POD_NAME.NAMESPACE SERVICE_NAME.NAMESPACE

# Performance validation
# Compare P99 latency pre/post upgrade
kubectl top pods -A --containers | grep envoy
```

**Success criteria:**
- All services returning 2xx responses
- No Envoy version skew warnings
- mTLS working across all service pairs
- External ingress traffic flowing
- P99 latency within 10% of baseline

## Rollback Strategy

**If things go wrong:**

1. **Traffic issues but cluster stable:** Restart deployments to refresh sidecars
2. **Widespread mesh failure:** Roll back to previous Istio version first, then consider GKE rollback
3. **GKE-level issues:** Create new node pool at old version, migrate workloads

The key insight: **Istio rollback is faster than GKE rollback.** If you're unsure whether the issue is mesh or infrastructure, try the Istio fix first.

---

**Next steps:** Confirm your current Istio version and I'll provide version-specific upgrade commands. The horror stories usually come from skipping the compatibility check or upgrading in the wrong order.