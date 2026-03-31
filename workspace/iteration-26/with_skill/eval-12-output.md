# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful sequencing to avoid breaking inter-service communication. Here's the safe path forward.

## Critical Order of Operations

**The golden rule: Upgrade the service mesh control plane BEFORE upgrading GKE nodes.** This ensures Istio can handle the new kubelet version and API changes.

### Phase 1: Pre-flight validation
```bash
# Check current Istio version
istioctl version

# Verify Istio 1.32 compatibility
# Istio typically supports K8s N-2 to N+1 versions
# For GKE 1.32, you need Istio 1.18+ (verify in Istio compatibility matrix)

# Check for deprecated APIs that affect Istio
kubectl get --raw /metrics | grep apiserver_request_total | grep deprecated
gcloud recommender insights list \
    --insight-type=google.container.DiagnosisInsight \
    --location=REGION \
    --project=PROJECT_ID \
    --filter="category.category:RELIABILITY"
```

### Phase 2: Upgrade Istio control plane (do this FIRST)
```bash
# Download compatible Istio version for K8s 1.32
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.20.2 TARGET_ARCH=x86_64 sh -

# Canary upgrade of Istio control plane
istioctl install --set values.pilot.env.EXTERNAL_ISTIOD=false --set revision=1-20-2

# Verify new control plane
kubectl get pods -n istio-system -l app=istiod

# Check webhook configurations aren't blocking
kubectl get validatingwebhookconfigurations | grep istio
kubectl get mutatingwebhookconfigurations | grep istio
```

### Phase 3: GKE control plane upgrade
```bash
# Apply maintenance exclusion to prevent auto-upgrades during mesh transition
gcloud container clusters update CLUSTER_NAME \
    --zone ZONE \
    --add-maintenance-exclusion-name "istio-upgrade-window" \
    --add-maintenance-exclusion-start-time 2024-12-XX \
    --add-maintenance-exclusion-end-time 2024-12-XX \
    --add-maintenance-exclusion-scope no_upgrades

# Upgrade control plane
gcloud container clusters upgrade CLUSTER_NAME \
    --zone ZONE \
    --master \
    --cluster-version 1.32.X-gke.XXXX

# Verify API server health with Istio
kubectl get pods -n istio-system
istioctl proxy-status
```

### Phase 4: Node pool upgrade strategy
```bash
# Conservative settings for mesh workloads
gcloud container node-pools update NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --max-surge-upgrade 1 \
    --max-unavailable-upgrade 0

# Upgrade nodes
gcloud container node-pools upgrade NODE_POOL_NAME \
    --cluster CLUSTER_NAME \
    --zone ZONE \
    --cluster-version 1.32.X-gke.XXXX
```

## Istio-Specific Risks & Mitigations

### 1. Envoy proxy version mismatch
**Risk:** New nodes get newer Envoy sidecars that can't communicate with old control plane
**Mitigation:** Upgrade Istio control plane first, validate proxy status before node upgrades

### 2. Admission webhook failures
**Risk:** Istio's mutating webhook rejects pod creation on new API server version
**Symptoms:** Pods fail to start with "admission webhook rejected the request"
```bash
# Check webhook health
kubectl get mutatingwebhookconfigurations istio-sidecar-injector -o yaml
kubectl logs -n istio-system -l app=istiod

# Temporary fix if webhooks fail
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
    -p '{"webhooks":[{"name":"rev.namespace.istio.io","failurePolicy":"Ignore"}]}'
```

### 3. Certificate rotation issues
**Risk:** Istio root CA certificates don't rotate properly during upgrade
```bash
# Monitor certificate health
istioctl proxy-config secret WORKLOAD_POD.NAMESPACE

# Check certificate expiry
kubectl get secrets -n istio-system | grep cacerts
kubectl get secret cacerts -n istio-system -o jsonpath='{.data.cert-chain\.pem}' | base64 -d | openssl x509 -text -noout
```

### 4. Service mesh dataplane disruption
**Risk:** Pod restarts during node upgrades break active connections
**Mitigation:**
```bash
# Validate PDBs for critical services
kubectl get pdb -A -o wide

# Check connection draining settings
kubectl get destinationrules -A -o yaml | grep -A5 connectionPool
```

## Mesh-Specific Validation Commands

### During upgrade
```bash
# Monitor proxy sync status
watch 'istioctl proxy-status'

# Check for configuration propagation delays
kubectl get endpointslices -A -l service.kubernetes.io/managed-by=endpoint-slice-mirroring-controller

# Validate mutual TLS
istioctl authn tls-check WORKLOAD_POD.NAMESPACE
```

### Post-upgrade validation
```bash
# Verify all sidecars injected and healthy
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].name}{"\n"}{end}' | grep istio-proxy

# Test cross-cluster communication (if multi-cluster)
istioctl proxy-config endpoints WORKLOAD_POD.NAMESPACE | grep HEALTHY

# Validate ingress gateway
kubectl get svc -n istio-system istio-ingressgateway
curl -I http://YOUR_GATEWAY_IP/healthz
```

## Rollback Plan

If mesh connectivity breaks:
1. **Control plane rollback:** `istioctl install --revision=PREVIOUS_VERSION`
2. **Restart workloads:** `kubectl rollout restart deployment -n NAMESPACE` to get old sidecars
3. **Node rollback:** Create new node pool at 1.31, migrate workloads, delete upgraded pool

## Timeline Recommendations

- **Dev/staging:** Complete mesh + GKE upgrade, soak for 48 hours
- **Production:** Schedule during lowest traffic window
- **Total window:** Plan 4-6 hours for full cluster (control plane: 30min, nodes: 2-4 hours depending on size)
- **Validation:** 30 minutes between each phase to catch issues early

## Common "Horror Story" Prevention

1. **Never upgrade GKE nodes before Istio control plane** — this causes version skew
2. **Test admission webhooks explicitly** — create a test pod after CP upgrade
3. **Monitor connection success rates** — don't just check pod status, verify actual traffic flows
4. **Have Istio experts on-call** — mesh issues require mesh expertise, not just K8s knowledge

**Key insight:** Most Istio upgrade horror stories come from upgrading GKE first or skipping the Istio compatibility validation. Follow this sequence religiously and you'll avoid the common pitfalls.

Remove the maintenance exclusion after successful validation:
```bash
gcloud container clusters update CLUSTER_NAME --zone ZONE --remove-maintenance-exclusion-name "istio-upgrade-window"
```