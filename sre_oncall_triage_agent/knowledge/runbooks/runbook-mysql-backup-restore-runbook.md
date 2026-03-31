---
metadata:
  kind: runbook
  status: draft
  summary: "Kubernetes MySQL backup/restore runbook: choose ConfigMap/PVC/cloud strategy by DB size, common failure patterns, and restore job examples."
  tags: ["mysql", "backup", "restore", "k8s"]
  first_action: "Assess DB size and pick backup path"
---

# MySQL Backup and Restore in Kubernetes Environments

## Problem Pattern
- **Category**: Database Backup and Recovery
- **Symptoms**: 
  * Unable to write database dumps to local filesystem
  * Permission denied errors when redirecting output
  * Need to backup database before changes or releases
- **Error Pattern**: `Permission denied` when trying to redirect MySQL dump to local filesystem

## Standard Investigation Process

### 1. Initial Assessment
- Determine database size and structure:
  ```bash
  # Check database size
  kubectl exec -n <namespace> <mysql-pod> -- mysql -u root -p<password> -e "SELECT table_schema, ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' FROM information_schema.tables GROUP BY table_schema;"
  
  # List largest tables
  kubectl exec -n <namespace> <mysql-pod> -- mysql -u root -p<password> -e "SELECT table_schema, table_name, ROUND((data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' FROM information_schema.tables ORDER BY (data_length + index_length) DESC LIMIT 10;"
  ```

- Check available storage in the cluster:
  ```bash
  kubectl get nodes -o=custom-columns=NAME:.metadata.name,ALLOCATABLE:.status.allocatable.memory,CAPACITY:.status.capacity.memory
  kubectl get pv
  ```

### 2. Common Causes
- Redirect (`>`) happens on local machine, not in container
- Local user doesn't have permission to write to target directory
- Kubernetes container isolation prevents direct local filesystem access
- Database too large for simple export methods

### 3. Resolution Steps

#### For Small Databases (< 1MB)
Use ConfigMap method:
```bash
# Create backup within pod
kubectl exec -n <namespace> <mysql-pod> -- bash -c "mysqldump -u root -p<password> --databases <database_name> > /tmp/db_backup.sql"

# Create ConfigMap from backup
kubectl create configmap mysql-backup-configmap -n <namespace> --from-file=/tmp/db_backup.sql=$(kubectl exec -n <namespace> <mysql-pod> -- cat /tmp/db_backup.sql)

# Export ConfigMap to YAML
kubectl get configmap mysql-backup-configmap -n <namespace> -o yaml > mysql-backup.yaml
```

#### For Medium to Large Databases
Use PersistentVolume method:
```bash
#MANUAL
# Create PVC for backup
kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: mysql-backup-pvc
  namespace: <namespace>
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: <required_size>Gi
EOF

# Create backup pod
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: mysql-backup-pod
  namespace: <namespace>
spec:
  containers:
  - name: mysql-backup
    image: mysql:5.7
    command:
    - /bin/bash
    - -c
    - "mysqldump -h <mysql-service>.<namespace>.svc.cluster.local -u root -p<password> --databases <database_name> > /backup/db_backup.sql && echo 'Backup completed' && tail -f /dev/null"
    volumeMounts:
    - name: backup-volume
      mountPath: /backup
  volumes:
  - name: backup-volume
    persistentVolumeClaim:
      claimName: mysql-backup-pvc
EOF

# Check backup status
kubectl logs -n <namespace> mysql-backup-pod
kubectl exec -n <namespace> mysql-backup-pod -- ls -la /backup
```

#### For Environments with Cloud Storage Access
Use cloud storage backup:
```bash
#MANUAL
# Create backup pod with cloud SDK
kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: mysql-backup-cloud
  namespace: <namespace>
spec:
  containers:
  - name: mysql-backup
    image: google/cloud-sdk:slim
    command:
    - /bin/bash
    - -c
    - "apt-get update && apt-get install -y default-mysql-client && mysqldump -h <mysql-service>.<namespace>.svc.cluster.local -u root -p<password> --databases <database_name> | gzip | gsutil cp - gs://<bucket-name>/mysql/$(date +%Y%m%d)/backup.sql.gz && echo 'Backup completed' && tail -f /dev/null"
  restartPolicy: OnFailure
EOF

# Check backup status
kubectl logs -n <namespace> mysql-backup-cloud
```

### 4. Database Restore Process

#### From ConfigMap
```bash
#MANUAL
# Apply ConfigMap
kubectl apply -f mysql-backup.yaml

# Create restore job
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: mysql-restore-job
  namespace: <namespace>
spec:
  template:
    spec:
      containers:
      - name: mysql-restore
        image: mysql:5.7
        command:
        - /bin/bash
        - -c
        - "cat /backup/db_backup.sql | mysql -h <mysql-service>.<namespace>.svc.cluster.local -u root -p<password>"
        volumeMounts:
        - name: backup-config
          mountPath: /backup
      volumes:
      - name: backup-config
        configMap:
          name: mysql-backup-configmap
      restartPolicy: Never
  backoffLimit: 4
EOF
```

#### From PersistentVolume
```bash
#MANUAL
# Create restore job
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: mysql-restore-job
  namespace: <namespace>
spec:
  template:
    spec:
      containers:
      - name: mysql-restore
        image: mysql:5.7
        command:
        - /bin/bash
        - -c
        - "cat /backup/db_backup.sql | mysql -h <mysql-service>.<namespace>.svc.cluster.local -u root -p<password>"
        volumeMounts:
        - name: backup-volume
          mountPath: /backup
      volumes:
      - name: backup-volume
        persistentVolumeClaim:
          claimName: mysql-backup-pvc
      restartPolicy: Never
  backoffLimit: 4
EOF
```

#### From Cloud Storage
```bash
#MANUAL
# Create restore job
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: mysql-restore-cloud
  namespace: <namespace>
spec:
  template:
    spec:
      containers:
      - name: mysql-restore
        image: google/cloud-sdk:slim
        command:
        - /bin/bash
        - -c
        - "apt-get update && apt-get install -y default-mysql-client && mkdir -p /tmp/backup && gsutil cp gs://<bucket-name>/mysql/<date>/backup.sql.gz /tmp/backup/ && gunzip /tmp/backup/backup.sql.gz && cat /tmp/backup/backup.sql | mysql -h <mysql-service>.<namespace>.svc.cluster.local -u root -p<password>"
      restartPolicy: Never
  backoffLimit: 4
EOF
```

## Automated Backup Solution

For production environments, implement a scheduled backup:

```bash
#MANUAL
# Create scheduled backup CronJob
kubectl apply -f - <<EOF
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mysql-backup-cronjob
  namespace: <namespace>
spec:
  schedule: "0 2 * * *"  # Daily at 2am
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: mysql-backup
            image: google/cloud-sdk:slim
            command:
            - /bin/bash
            - -c
            - |
              apt-get update && apt-get install -y default-mysql-client
              BACKUP_FILE="/tmp/backup-$(date +%Y%m%d-%H%M%S).sql.gz"
              echo "Starting backup to $BACKUP_FILE"
              mysqldump -h <mysql-service>.<namespace>.svc.cluster.local -u root -p<password> --databases <database_name> | gzip > $BACKUP_FILE
              echo "Uploading to cloud storage"
              gsutil cp $BACKUP_FILE gs://<bucket-name>/mysql/$(date +%Y%m%d)/
              echo "Backup completed"
          restartPolicy: OnFailure
EOF
```

## Prevention
- Implement scheduled backup solution
- Create database operator for automated management
- Store credentials in Kubernetes secrets
- Monitor backup jobs and set up alerting
- Document backup and restore procedures

## Example Case
- Reference: DB_MYSQL_BACKUP_20250520
- Specific Commands Used:
  ```bash
  #MANUAL
  # Check database size
  kubectl exec -n prod fp-mysql-0 -- mysql -u root -ppassword -e "SELECT table_schema, ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'Size (MB)' FROM information_schema.tables GROUP BY table_schema;"
  
  # Create PVC for backup
  kubectl apply -f backup-pvc.yaml
  
  # Create backup pod
  kubectl apply -f mysql-backup-pod.yaml
  ```
- Resolution Summary: Implemented PersistentVolume-based backup solution with verification and documented restore procedure 
