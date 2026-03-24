# GKE + Istio Upgrade Plan: 1.31 → 1.32

Service mesh upgrades require careful sequencing to avoid breaking traffic flow. Here's your battle-tested approach:

## Upgrade Order (Critical)

**Always upgrade Istio BEFORE upgrading GKE nodes** — this is the key to avoiding mesh breakage:

1. **Istio control plane** (istiod) first
2. **GKE control plane** (1.31 → 1.32) 
3. **Istio data plane** (sidecars)
4. **GKE node pools** last

This sequence ensures the mesh control plane can handle both old and new Kubernetes API versions during the transition.

## Pre-Upgrade Validation

### Istio Version Compatibility
```bash
# Check your current Istio version
kubectl get deployment istiod -n istio-system -o jsonpath='{.spec.template.spec.containers[0].image}'

# Verify Istio 1.20+ supports K8s 1.32 
# Check https://istio.io/latest/docs/releases/supported-releases/
```

**Critical:** Istio versions before 1.19 may not support K8s 1.32. If you're on an older Istio, upgrade Istio first.

### Current Mesh Health
```bash
# Istio control plane status
kubectl get pods -n istio-system
istioctl proxy-status

# Check for any failing sidecars
kubectl get pods -A -o jsonpath='{range .items[*]}{.metadata.namespace}{" "}{.metadata.name}{" "}{.spec.containers[*].name}{"\n"}{end}' | grep istio-proxy | head -10

# Validate mesh configuration
istioctl analyze -A
```

## Step-by-Step Upgrade Runbook

### Step 1: Upgrade Istio Control Plane

```bash
# Download target Istio version (example: 1.20.x for K8s 1.32 support)
curl -L https://istio.io/downloadIstio | ISTIO_VERSION=1.20.2 sh -
cd istio-1.20.2
export PATH=$PWD/bin:$PATH

# Backup current Istio configuration
kubectl get configmap istio -n istio-system -o yaml > istio-config-backup.yaml
kubectl get gateway -A -o yaml > gateways-backup.yaml
kubectl get virtualservice -A -o yaml > virtualservices-backup.yaml

# Upgrade control plane
istioctl upgrade --set values.pilot.env.EXTERNAL_ISTIOD=false

# Verify control plane health
kubectl get pods -n istio-system
istioctl proxy-status
```

**Validation checkpoint:** All istiod pods running, proxy-status shows no STALE entries.

### Step 2: Upgrade GKE Control Plane

```bash
# Configure maintenance window for off-peak hours
gcloud container clusters update CLUSTER_NAME \
  --zone ZONE \
  --maintenance-window-start "2024-12-15T02:00:00Z" \
  --maintenance-window-end "2024-12-15T06:00:00Z" \
  --maintenance-window-recurrence "FREQ=WEEKLY;BYDAY=SUN"

# Upgrade control plane to 1.32
gcloud container clusters upgrade CLUSTER_NAME \
  --zone ZONE \
  --master \
  --cluster-version 1.32.0-gke.1200

# Verify (wait 10-15 minutes)
kubectl get pods -n kube-system
kubectl get pods -n istio-system
```

**Validation checkpoint:** kube-system pods healthy, Istio control plane still responding.

### Step 3: Test Mesh Connectivity

```bash
# Deploy test workloads to verify mesh works with new CP
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app-a
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app-a
  template:
    metadata:
      labels:
        app: test-app-a
    spec:
      containers:
      - name: app
        image: nginx:alpine
        ports:
        - containerPort: 80
---
apiVersion: v1
kind: Service
metadata:
  name: test-app-a
  namespace: default
spec:
  selector:
    app: test-app-a
  ports:
  - port: 80
EOF

# Verify sidecar injection still works
kubectl label namespace default istio-injection=enabled --overwrite
kubectl rollout restart deployment test-app-a

# Check sidecar attached
kubectl get pods -l app=test-app-a -o jsonpath='{.items[0].spec.containers[*].name}'
# Should show: app istio-proxy

# Test service-to-service communication
kubectl run test-client --image=curlimages/curl --rm -it --restart=Never -- curl -s test-app-a.default.svc.cluster.local
```

### Step 4: Rolling Sidecar Restart (Data Plane Upgrade)

```bash
# Restart all workloads to get new sidecar version
# Do this namespace by namespace for large clusters

# List namespaces with sidecars
kubectl get namespace -l istio-injection=enabled

# Rolling restart per namespace (adjust batch size for your tolerance)
for ns in $(kubectl get namespace -l istio-injection=enabled -o name | cut -d/ -f2); do
  echo "Restarting deployments in $ns"
  kubectl rollout restart deployment -n $ns
  # Wait for rollout to complete before next namespace
  kubectl rollout status deployment -n $ns --timeout=600s
done

# Verify new sidecar versions
istioctl proxy-status | head -20
```

### Step 5: Upgrade Node Pools

```bash
# Configure conservative surge settings for mesh workloads
gcloud container node-pools update default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --max-surge-upgrade 1 \
  --max-unavailable-upgrade 0

# Upgrade nodes (this will cause pod restarts)
gcloud container node-pools upgrade default-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.32.0-gke.1200

# Monitor progress - watch for networking issues
watch 'kubectl get nodes -o wide'
watch 'kubectl get pods -n istio-system'
```

## Mesh-Specific Watch-Outs

### 1. Admission Webhooks (Critical)
Istio's sidecar injector webhook may reject pods on the new K8s version:

```bash
# Check webhook status during upgrade
kubectl get validatingwebhookconfigurations istio-validator-istio-system
kubectl get mutatingwebhookconfigurations istio-sidecar-injector

# If pods fail to create, check events
kubectl get events -A --field-selector reason=FailedCreate | grep webhook
```

**Emergency fix if webhook blocks pod creation:**
```bash
# Temporarily set failure policy to Ignore
kubectl patch mutatingwebhookconfigurations istio-sidecar-injector \
  -p '{"webhooks":[{"name":"rev.namespace.sidecar-injector.istio.io","failurePolicy":"Ignore"}]}'
```

### 2. Envoy Compatibility
Watch for Envoy errors in sidecar logs:
```bash
# Check for Envoy startup errors on new nodes
kubectl logs -l app=your-app -c istio-proxy --tail=50 | grep -i error

# Common error: "upstream connect error or disconnect/reset before headers"
# Usually indicates config sync issues between istiod and sidecars
```

### 3. mTLS Certificate Rotation
During the upgrade, certificate rotation may cause brief connection failures:
```bash
# Check certificate status
istioctl authn tls-check POD_NAME.NAMESPACE.svc.cluster.local

# Monitor for certificate errors
kubectl logs -n istio-system deployment/istiod | grep -i cert
```

### 4. Gateway Traffic Interruption
Ingress traffic may be briefly interrupted during node pool upgrades:
```bash
# Check gateway pod placement
kubectl get pods -n istio-system -l app=istio-ingressgateway -o wide

# Verify LoadBalancer endpoints
kubectl get svc -n istio-system istio-ingressgateway
```

## Pre-Flight Checklist

```markdown
## Istio + GKE Upgrade Pre-Flight

Infrastructure
- [ ] Current GKE: 1.31 | Target: 1.32
- [ ] Current Istio version: ___ | Target: ___ (must support K8s 1.32)
- [ ] Maintenance window: ___ (allow 4-6 hours total)
- [ ] Rollback plan documented

Istio Health
- [ ] All istiod pods healthy: `kubectl get pods -n istio-system`
- [ ] No STALE proxies: `istioctl proxy-status`
- [ ] No config issues: `istioctl analyze -A`
- [ ] Gateway traffic flowing: test ingress endpoints
- [ ] Inter-service mTLS working: test service-to-service calls

Backup
- [ ] Istio configuration exported
- [ ] Gateway/VirtualService configs backed up
- [ ] Current mesh traffic patterns documented

Monitoring
- [ ] Service mesh observability active (Kiali/Jaeger if used)
- [ ] Alert thresholds adjusted for upgrade window
- [ ] On-call team notified
```

## Rollback Strategy

If things go wrong:

**Control plane issues:**
```bash
# Rollback Istio control plane
istioctl install --set revision=previous-version

# Restart pods to get old sidecars
kubectl rollout restart deployment -n NAMESPACE
```

**Node pool issues:**
```bash
# Create new pool at 1.31, migrate workloads, delete problematic pool
gcloud container node-pools create rollback-pool \
  --cluster CLUSTER_NAME \
  --zone ZONE \
  --cluster-version 1.31.X-gke.XXXX
```

## Post-Upgrade Validation

```bash
# Istio health
istioctl proxy-status | grep STALE  # Should be empty
kubectl get pods -n istio-system    # All running

# Traffic flow
curl -v https://your-ingress-endpoint/health
kubectl run test-client --rm -it --image=curlimages/curl -- curl service-a.namespace.svc.cluster.local

# No connection errors in sidecar logs
kubectl logs -l app=critical-app -c istio-proxy --tail=100 | grep -i "connection\|error"

# mTLS working
istioctl authn tls-check service-a.namespace.svc.cluster.local
```

**Key Success Metric:** Zero service mesh connectivity errors post-upgrade. All `istioctl proxy-status` entries show SYNCED.

The critical insight: **Istio first, nodes last**. This sequence has saved countless mesh operators from the horror stories you've heard about.