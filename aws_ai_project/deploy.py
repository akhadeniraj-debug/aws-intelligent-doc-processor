"""
Automated 1-Click AWS Deployer for Intelligent Document Processor
Deploys using AWS SAM.
"""

import os
import sys

def deploy():
    print("🚀 Deploying Intelligent Document Processor to AWS...")
    print("Building with SAM...")
    build_res = os.system("sam build")
    if build_res != 0:
        print("❌ SAM build failed. Make sure AWS SAM CLI is installed.")
        sys.exit(1)
        
    print("Deploying with SAM...")
    deploy_res = os.system("sam deploy --resolve-s3 --stack-name intelligent-doc-processor-stack --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND CAPABILITY_NAMED_IAM")
    
    if deploy_res == 0:
        print("\n🎉 Deployment Complete!")
    else:
        print("\n❌ Deployment Failed.")
        sys.exit(1)

if __name__ == "__main__":
    deploy()
