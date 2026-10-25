with Diagram("AWS Services Flow - Salesforce Connect Cases Integration", show=False, direction="LR"):
    
    # External systems
    with Cluster("External Systems"):
        salesforce = User("Salesforce\nCRM")
        connect = Connect("Amazon Connect\nCases")
    
    # EventBridge layer
    with Cluster("Event Processing"):
        partner_bus = Eventbridge("Partner\nEvent Bus")
        default_bus = Eventbridge("Default\nEvent Bus")
    
    # Queue layer
    with Cluster("Message Queuing"):
        sf_queue = SQS("Salesforce\nQueue")
        connect_queue = SQS("Connect\nQueue")
    
    # Processing layer
    with Cluster("Orchestration"):
        sf_stepfunc = StepFunctions("Salesforce to Connect\nStep Function")
        connect_stepfunc = StepFunctions("Connect to Salesforce\nStep Function")
    
    # Lambda functions
    with Cluster("Processing Functions"):
        sf_lambda = Lambda("SF Queue\nProcessor")
        connect_lambda = Lambda("Connect Queue\nProcessor")
        sf_api_lambda = Lambda("SF API\nProcessor")
        connect_api_lambda = Lambda("Connect API\nProcessor")
    
    # Flow 1: Salesforce to Connect
    salesforce >> Edge(label="Case Events") >> partner_bus >> sf_queue >> sf_stepfunc
    sf_stepfunc >> sf_lambda >> connect_api_lambda >> Edge(label="Create/Update") >> connect
    
    # Flow 2: Connect to Salesforce  
    connect >> Edge(label="Case Events") >> default_bus >> connect_queue >> connect_stepfunc
    connect_stepfunc >> connect_lambda >> sf_api_lambda >> Edge(label="Create/Update") >> salesforce
