---
metadata:
  kind: runbook
  status: draft
  summary: "Runbook for Jenkins S3 upload 403/AccessDenied: confirm caller identity, then locate explicit deny across IAM/bucket policy/VPC-IP conditions; treat policy changes as `#MANUAL`."
  tags: ["jenkins", "s3", "iam", "access-denied"]
  first_action: "Run `aws sts get-caller-identity`"
---

# Issue Type: Jenkins
## Problem Pattern
- Category: AWS S3 Permission Issues
- Symptoms:
  * Jenkins build fails with S3 upload errors
  * "Access Denied" or "Permission Denied" errors when attempting to upload to S3
  * Error messages containing `com.amazonaws.services.s3.model.AmazonS3Exception`
  * HTTP Status Code 403 in error messages
  * Error message refers to "explicit deny in a resource-based policy"
- Alert Pattern: Jenkins job failure notifications via email or Slack

## Standard Investigation Process

### 1. Initial Assessment
- Review Jenkins console output to identify the exact error message
- Note the AWS user/role being used (look for ARN in error message)
- Identify the target S3 bucket and path
- Check for "explicit deny" messages which indicate a policy-based restriction
- **Identify the network source** of the Jenkins agent (important for VPC/IP-based policies)
- Commands to run:
  ```bash
  # Check AWS identity in use
  aws sts get-caller-identity
  
  # Verify S3 bucket access (read)
  aws s3 ls s3://[bucket-name]/
  
  # Check bucket policy
  aws s3api get-bucket-policy --bucket [bucket-name]
  
  # Check network location of Jenkins agent
  aws ec2 describe-instances --filters "Name=private-ip-address,Values=[agent-ip]" --query "Reservations[].Instances[].{InstanceId:InstanceId,VpcId:VpcId,PrivateIpAddress:PrivateIpAddress,SubnetId:SubnetId}"
  ```

### 2. Common Causes
- **IAM User Policy Issue**: The IAM user lacks proper permissions or has an explicit deny
  * Check user policies with: `aws iam list-attached-user-policies --user-name [username]`
  * Check inline policies with: `aws iam list-user-policies --user-name [username]`
  
- **S3 Bucket Policy Issue**: The bucket policy explicitly denies access to the user
  * Review bucket policy with: `aws s3api get-bucket-policy --bucket [bucket-name]`
  * Look for deny statements that match the user ARN or wild patterns
  
- **Network-based Restrictions**: The bucket policy restricts access to specific VPCs or IP ranges
  * Look for conditions using `aws:sourceVpc` or `aws:sourceIp` in bucket policies
  * Check if Jenkins agent is running in an allowed VPC or from an allowed IP range
  * This is a common issue in secure environments where S3 access is restricted to specific networks
  
- **Permission Boundary**: A permission boundary may be restricting the user
  * Check for permission boundaries: `aws iam get-user --user-name [username]`
  
- **Resource-based Policy**: A resource policy on the specific object or prefix
  * Check ACLs: `aws s3api get-object-acl --bucket [bucket] --key [object-key]`
  
- **Credential Issue**: Expired or invalid credentials
  * Verify identity: `aws sts get-caller-identity`
  * Check if using correct credential ID in Jenkins

### 3. Resolution Steps
1. **Identify the Policy Causing the Denial**:
   - Examine all policies for explicit deny statements
   - Pay special attention to network conditions (VPC or IP restrictions)
   * Check for conditions like IP restrictions or timestamp conditions
   
2. **For Network-Based Restrictions**:
    ```bash
    #MANUAL
    # Check Jenkins agent VPC
    aws ec2 describe-instances --filters "Name=private-ip-address,Values=[agent-ip]" --query "Reservations[].Instances[].VpcId"
   
    # Update bucket policy to include Jenkins agent VPC
    aws s3api get-bucket-policy --bucket [bucket-name] > original_policy.json
   # Manually edit the policy to include Jenkins VPC in aws:sourceVpc condition arrays
    aws s3api put-bucket-policy --bucket [bucket-name] --policy file://updated_policy.json
   
    # Alternative: Set up VPC endpoint for S3 in Jenkins VPC
    aws ec2 create-vpc-endpoint --vpc-id [jenkins-vpc-id] --service-name com.amazonaws.region.s3 --route-table-ids [route-table-id]
    ```
   
3. **Modify IAM User Policy** (may not override network denies):
    ```bash
    #MANUAL
    # Add S3 permissions to user
    aws iam put-user-policy --user-name [username] --policy-name S3Access --policy-document '{
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:PutObject",
                   "s3:GetObject",
                   "s3:ListBucket"
               ],
               "Resource": [
                   "arn:aws:s3:::[bucket-name]",
                   "arn:aws:s3:::[bucket-name]/*"
               ]
           }
       ]
    }'
    ```

4. **Update S3 Bucket Policy**:
    ```bash
    #MANUAL
    # Modify bucket policy to allow access
    aws s3api put-bucket-policy --bucket [bucket-name] --policy '[MODIFIED_POLICY_JSON]'
    ```

5. **Move Jenkins Agent to Approved Network**:
   - Deploy Jenkins agent in approved VPC
   - Connect through approved VPN IP address
   - Use appropriate network security group rules

6. **Use Different Credentials**:
   - Update Jenkins credential configuration to use a different IAM user/role
   - Configure proper cross-account access if needed

7. **Verify Resolution**:
   ```bash
   # Test upload access
   aws s3 cp test.txt s3://[bucket-name]/test.txt
   
   # Clean up
   aws s3 rm s3://[bucket-name]/test.txt
   ```

### 4. Prevention
- Implement proper IAM access reviews on a regular cadence
- Use IAM Access Analyzer to identify potentially risky policies
- Document all S3 buckets used by Jenkins jobs and their required permissions
- **Document network requirements for Jenkins agents accessing S3**
- **Deploy Jenkins agents in approved VPCs with S3 VPC endpoints**
- **Implement clear error handling for network-related S3 access issues**
- Set up monitoring for S3 access denials using CloudTrail
- Implement a testing process for credential rotation to verify permissions
- Use credential rotation on a regular schedule

## Example Case
- Reference: JENKINS_14635
- Specific Issue: Network-based restriction in S3 bucket policy
- Specific Commands Used:
  ```bash
  #MANUAL
  # Check user policies
  aws iam list-attached-user-policies --user-name CronProd
  aws iam list-user-policies --user-name CronProd
  
  # Check bucket policy
  aws s3api get-bucket-policy --bucket datavisor-staging-uswest2
  
  # Check Jenkins agent network location
  aws ec2 describe-instances --filters "Name=private-ip-address,Values=192.168.116.26" --query "Reservations[].Instances[].{InstanceId:InstanceId,VpcId:VpcId}"
  
  # Update bucket policy to include Jenkins agent VPC
  aws s3api get-bucket-policy --bucket datavisor-staging-uswest2 > original_policy.json
  # Edit policy to include Jenkins VPC in aws:sourceVpc condition arrays
  aws s3api put-bucket-policy --bucket datavisor-staging-uswest2 --policy file://updated_policy.json
  ```
  
- Resolution Summary:
  The Jenkins job was failing because the bucket policy had network-based restrictions that only allowed access from specific VPCs and VPN IP addresses. The bucket policy included explicit "DenyNotVPCNotVPN" and "AllowVPC"/"AllowVPN" statements. The Jenkins agent was running in a VPC that wasn't included in the allowed networks list. The solution was to modify the bucket policy to include the Jenkins agent's VPC in the allowed networks list, allowing the CronProd user to successfully upload to S3 from the Jenkins agent. 
