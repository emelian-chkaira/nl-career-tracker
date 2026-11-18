"""Keyword -> company clusters. A search term maps to clusters of Dutch employers; each company is then resolved to its own website,
career page and ATS, and its NL jobs are fetched directly (no job-board middlemen). Format: 'Name' or 'Name|domain.tld' when the domain is certain."""
C = {
 "semiconductor": ("semiconductor chip lithography wafer photonics euv optics fab ic design embedded fpga asic cleanroom nanotech mems",
  ["ASML|asml.com", "NXP Semiconductors|nxp.com", "Nexperia|nexperia.com", "ASM International|asm.com", "BE Semiconductor Industries|besi.com", "Prodrive Technologies|prodrive-technologies.com", "VDL ETG|vdletg.com",
   "Ampleon|ampleon.com", "Smart Photonics|smartphotonics.com", "PhotonDelta", "Effect Photonics|effectphotonics.com", "Sencio", "Axelera AI|axelera.ai", "Chipsurance", "Technolution|technolution.eu", "Mapper Lithography", "NTS Group|nts-group.nl",
   "Frencken Europe|frencken.com", "Neways Electronics|neways.com", "Sioux Technologies|sioux.eu", "Demcon|demcon.com", "Settels Savenije", "Mecal", "MI-Partners|mi-partners.nl", "Bruker", "Thermo Fisher Scientific|thermofisher.com", "JEOL", "Zeiss|zeiss.com",
   "TMC", "Sigma Designs", "Ultratech", "Applied Materials", "Lam Research|lamresearch.com", "KLA", "Cadence|cadence.com", "Synopsys|synopsys.com", "Siemens EDA", "Infineon|infineon.com", "STMicroelectronics", "Silicon Austria", "IMEC", "Holst Centre", "Eindhoven Engine", "Photonic Integration Technology Center"]),
 "hightech": ("high-tech hardware mechatronics robotics systems engineering mechanical optical precision automation manufacturing industrial machine vision control",
  ["Philips|philips.com", "Signify|signify.com", "TNO|tno.nl", "Thales Nederland|thalesgroup.com", "Fokker Technologies", "GKN Fokker", "Airbus Netherlands", "Damen Shipyards|damen.com", "DAF Trucks|daf.com", "VDL Groep|vdlgroep.com", "Fugro|fugro.com",
   "Océ", "Canon Production Printing|cpp.canon", "Vanderlande|vanderlande.com", "Dutch Space", "Airborne", "Lely|lely.com", "Marel", "Philips Medical Systems", "Tennet|tennet.eu", "ITER", "DIFFER", "Nikhef", "SRON", "ASTRON|astron.nl", "ESA ESTEC", "Hyperion", "Lightyear",
   "Bosch Rexroth", "Festo", "Brainport Development", "Zuyd", "Delft Dynamics", "Tellurium", "Vitestro", "Neways", "Berghof", "Hittech", "Boschman", "Ocean Optics", "TKH Group|tkhgroup.com", "Heidenhain", "Teledyne DALSA", "Smart Robotics", "Rovco", "RoboHouse", "Fizyr", "Delft Robotics"]),
 "software": ("software developer engineer backend frontend fullstack saas platform cloud api microservices web",
  ["Adyen|adyen.com", "Mollie|mollie.com", "bunq|bunq.com", "Picnic|picnic.app", "bol.com|bol.com", "Coolblue|coolblue.nl", "Booking.com|booking.com", "TomTom|tomtom.com", "Elastic|elastic.co", "Backbase|backbase.com", "Mendix|mendix.com", "Bird|bird.com",
   "Catawiki|catawiki.com", "Bynder|bynder.com", "Studocu|studocu.com", "Framer|framer.com", "Miro|miro.com", "Sendcloud|sendcloud.com", "Bitvavo|bitvavo.com", "Ohpen|ohpen.com", "Temper|temper.works", "Optiver|optiver.com", "IMC Trading|imc.com",
   "Flow Traders|flowtraders.com", "Exact|exact.com", "AFAS Software|afas.nl", "Visma", "Unit4|unit4.com", "Mews|mews.com", "Pega", "Topicus|topicus.com", "Effectory", "Lightspeed", "Messagebird", "Swapfiets|swapfiets.com", "Mambu|mambu.com", "Lightyear|lightyear.com",
   "Dataiku", "Sentry", "JetBrains", "Personio", "Check Technologies", "Triple", "Sana Commerce|sanacommerce.com", "Oracle", "Bizzomate", "Ximedes", "Rockstars IT", "Itility|itility.nl", "Schuberg Philis|schubergphilis.com", "Cegeka|cegeka.com", "Ordina|ordina.nl",
   "Xebia|xebia.com", "Info Support|infosupport.com", "Mirabeau", "Mobiquity|mobiquityinc.com", "Merapar|merapar.com", "DEPT|deptagency.com", "Q42|q42.nl", "Yonder", "Codesmith", "iO Digital", "Hoppinger", "Tweede Golf", "Cloud Nine", "Eneco", "Moneyou", "Takeaway.com", "Just Eat Takeaway|justeattakeaway.com",
   "Springer Nature", "Wolters Kluwer|wolterskluwer.com", "RELX|relx.com", "Elsevier", "Kadaster", "Rijkswaterstaat|werkenvoornederland.nl", "Centric|centric.eu", "Conclusion", "Atos", "Capgemini|capgemini.com", "Sogeti", "CGI|cgi.com", "Accenture|accenture.com"]),
 "mobile": ("mobile ios android flutter react native app swift kotlin",
  ["Mobiquity|mobiquityinc.com", "Mirabeau", "Yonder", "Q42|q42.nl", "Triple", "Cloud Nine", "Tapptic", "The Mobile Company", "Fabrique|fabrique.nl", "Hike One", "Ambassadors", "iO Digital", "Wunderman Thompson", "Appsolutely", "Kyra", "Kramp", "Vinted", "Wolt", "Uber|uber.com", "Bolt", "Swapfiets|swapfiets.com", "Picnic|picnic.app", "TIER", "Felyx", "Lightyear", "Blendle", "Yoair", "Buurtaal", "Studyflix", "Peerby", "Gaming Realms", "Mobile Dev Agency"]),
 "ai": ("ai machine learning data science nlp llm computer vision deep learning analytics data engineer",
  ["Nebius", "Pailot", "Twin", "Conversation Design Institute", "Cultivator", "Dataiku", "Databricks|databricks.com", "Snowflake", "Axelera AI|axelera.ai", "Bright Cape", "Eagle Eye", "Zorg AI", "Prophecy", "Ynformed", "Ortec|ortec.com", "Quantib", "ThirdAI", "Sentient", "Deeploy", "Fruition", "Sentiance", "Photoroom", "Pluvo", "Sensing Feelings", "Trifork", "Schiphol", "SURF|surf.nl", "TNO", "Philips Research", "Rabobank AI", "ING Analytics", "Bol AI", "Booking AI", "Uber Amsterdam", "Netflix Amsterdam", "NVIDIA", "Microsoft", "Google|google.com", "Amazon|amazon.jobs", "Meta"]),
 "security": ("security cyber infosec pentest soc iam appsec privacy compliance",
  ["Fox-IT|fox-it.com", "NCC Group", "Northwave|northwave-cybersecurity.com", "Eye Security|eye.security", "Secura", "Zerocopter", "Cybersprint", "Hackerone", "Madison Gurkha", "Computest", "Cyber Security Works", "Kaspersky", "Bitdefender", "Palo Alto Networks", "CrowdStrike", "Check Point", "Sophos", "Tesorion", "Nixu", "Sentinels", "Surf security", "NCSC", "Shadowserver", "IntelliGuard", "Resilience"]),
 "data": ("data engineer analytics bi big data dwh etl lakehouse sql",
  ["Snowflake", "Databricks|databricks.com", "Confluent", "dbt Labs", "Matillion", "Fivetran", "Talend", "Alteryx", "Tableau", "Qlik", "GoDataDriven", "Data Science Lab", "Brightfish", "Anchormen", "Vantage", "Eraneos", "Rabobank", "ING|ing.com", "ABN AMRO|abnamro.com", "Achmea", "Nationale-Nederlanden", "Aegon", "ASR", "KPN|kpn.com", "VodafoneZiggo", "Odido", "Ahold Delhaize|aholddelhaize.com", "Albert Heijn"]),
 "gaming": ("game gaming unity unreal games studio engine",
  ["Guerrilla Games|guerrilla-games.com", "Nixxes", "Vlambeer", "Ronimo Games", "Triumph Studios", "Paradox Interactive", "Jagex", "Azerion|azerion.com", "Abbey Games", "Guerrilla", "Force Field", "Little Chicken", "Codeglue", "Spil Games", "Gamebasics", "Tamalaki", "Cloud Imperium", "Keen Games", "Sumo Digital", "Playrix", "Kingsisle", "Supercell", "Mojang", "King", "Playsoft", "Fantasy Studio", "Vanguard", "Hutch"]),
 "devops": ("devops cloud kubernetes sre platform infrastructure aws azure gcp terraform sysadmin network",
  ["Schuberg Philis|schubergphilis.com", "Itility|itility.nl", "Cloud Nine", "Xebia|xebia.com", "Binx", "Mission", "Oblivion", "Kubermatic", "Equinix", "Interxion", "Digital Realty", "NorthC|northcdatacenters.com", "Eurofiber", "KPN|kpn.com", "Solvinity", "True", "Previder", "Leaseweb|leaseweb.com", "TransIP", "Hostnet", "Hetzner", "OVH", "Cloudflare|cloudflare.com", "Datadog|datadoghq.com", "GitLab|gitlab.com", "HashiCorp", "Elastic|elastic.co", "SURF|surf.nl", "AMS-IX|ams-ix.net", "NL-ix", "Sentia", "Nedap|nedap.com"]),
 "fintech": ("fintech payments banking trading crypto insurtech wealth lending",
  ["Adyen|adyen.com", "Mollie|mollie.com", "bunq|bunq.com", "Bitvavo|bitvavo.com", "Ohpen|ohpen.com", "Optiver|optiver.com", "IMC Trading|imc.com", "Flow Traders|flowtraders.com", "Mambu|mambu.com", "Knab", "Moneyou", "Lightyear", "Tikkie", "Bux", "DEGIRO", "Finaps", "Brightlink", "Qover", "Wefox", "Backbase|backbase.com", "Ebury", "Visma", "Exact", "Twinfield", "Yuki", "Moneybird", "Rabobank|rabobank.com", "ING|ing.com", "ABN AMRO|abnamro.com", "Worldline", "Payvision", "Ingenico", "Nuvei", "Checkout.com", "Stripe", "Klarna", "Wise", "Revolut", "N26", "Trade Republic", "Tink", "Plaid", "Bitfury", "Coinbase", "Kraken", "Binance"]),
 "healthtech": ("health medtech healthcare biotech medical imaging ehr",
  ["Philips|philips.com", "Quantib", "Pie Medical", "Neuroscouts", "Nedap", "Zorgdomein", "Topicus Zorg", "Nictiz", "Prosus", "Kenniscentrum", "Elekta", "Siemens Healthineers", "GE Healthcare", "Medtronic", "Thermo Fisher|thermofisher.com", "Qiagen", "Genmab", "Argenx", "uniQure", "Pharming", "Mimetas", "Crucell", "Janssen", "DSM|dsm-firmenich.com", "Eurofins", "Sanquin", "Radboudumc", "UMC Utrecht|umcutrecht.nl", "Erasmus MC", "Amsterdam UMC", "Leiden UMC", "Maastricht UMC"]),
 "energy": ("energy cleantech grid smart energy solar hydrogen battery sustainability",
  ["Eneco|eneco.com", "Vattenfall", "Alliander|alliander.com", "TenneT|tennet.eu", "Stedin", "Enexis", "Gasunie", "Shell|shell.com", "BP", "Fluor", "Shell Projects", "Heerema", "Boskalis", "Royal HaskoningDHV|royalhaskoningdhv.com", "Arcadis|arcadis.com", "Sweco", "Witteveen+Bos", "Lightyear", "Sunrock", "Solarcentury", "GroenLeven", "Tesla", "Tesla Netherlands", "Allego", "Fastned|fastned.nl", "Vattenfall Netherlands", "ENGIE", "Powerdale", "Sympower", "Sonnen", "Lion Smart", "LeydenJar", "Nedstack", "Ebusco", "Hyzon", "Frames", "Ecoloop"]),
 "consulting": ("consultancy it services consulting detachering recruitment sap erp implementation",
  ["Capgemini|capgemini.com", "Sogeti|sogeti.com", "Accenture|accenture.com", "CGI|cgi.com", "Cognizant", "Deloitte", "PwC", "KPMG", "EY", "Atos", "Computacenter", "Bechtle", "Ordina|ordina.nl", "Conclusion", "Centric|centric.eu", "Capgemini Engineering", "Brunel", "Yacht", "Randstad", "Hays", "Michael Page", "Talentbird", "Young Capital", "Valtech", "Eraneos", "Infosys", "TCS", "Wipro", "HCL", "Tech Mahindra", "NTT Data", "Kyndryl", "DXC", "Unisys", "Rackspace", "Detach", "Hyperion", "Rubix", "Axxes", "TriOpSys", "Inergy", "LogicaCMG", "Wortell", "Macaw", "Triple", "Sopra Steria"]),
 "ecommerce": ("ecommerce e-commerce retail marketplace logistics supply chain delivery",
  ["bol.com|bol.com", "Coolblue|coolblue.nl", "Picnic|picnic.app", "Catawiki|catawiki.com", "Zalando", "Wehkamp", "Marktplaats|marktplaats.nl", "Ahold Delhaize|aholddelhaize.com", "Albert Heijn", "Jumbo", "HEMA", "Rituals", "Action", "MediaMarkt", "Bax Music", "Sendcloud|sendcloud.com", "PostNL", "DHL", "DPD", "Cycloon", "Vinted", "Otrium", "Lightspeed", "Magento", "Adyen", "Mollie", "Kramp Group", "Booking.com", "Airbnb", "GetYourGuide", "Eventbrite", "TicketSwap", "Swapfiets", "Trivago", "Uber", "Bolt", "Takeaway.com"]),
 "telecom": ("telecom network 5g wireless satellite radio mobile network infrastructure",
  ["KPN|kpn.com", "VodafoneZiggo", "Odido", "Eurofiber", "Ericsson", "Nokia", "Huawei", "Cisco", "Juniper", "Ciena", "Infinera", "Tele2", "Lyca", "Netherlands Space Office", "ISISpace", "NLR|nlr.nl", "Airbus Defence", "Hyperion"]),
 "automotive": ("automotive ev electric vehicle autonomous driving mobility",
  ["DAF Trucks|daf.com", "VDL Groep|vdlgroep.com", "Lightyear", "Tesla", "Fastned", "Ebusco", "Lucid", "Polestar", "Stellantis", "Toyota", "BMW", "TomTom|tomtom.com", "NXP|nxp.com", "Siemens Digital Industries", "Bosch", "Continental", "Valeo", "ZF", "Hyundai", "Vanmoof", "Swapfiets", "TIER", "Felyx", "Greenwheels", "Arval", "LeasePlan", "Athlon", "Tata Steel"]),
 "bigtech": ("big tech faang software engineer cloud ai amazon google microsoft apple meta netflix uber stripe spotify",
  ["Databricks|databricks.com", "Microsoft|microsoft.com", "Google|google.com", "Amazon|amazon.jobs", "Uber|uber.com", "Booking.com|booking.com", "Meta|metacareers.com", "Netflix|netflix.com", "Optiver|optiver.com", "IMC Trading|imc.com",
   "Flow Traders|flowtraders.com", "Apple|apple.com", "GitHub|github.com", "HashiCorp|hashicorp.com", "Elastic|elastic.co", "Miro|miro.com", "Spotify|spotify.com", "Stripe|stripe.com", "Adyen|adyen.com", "WeTransfer|wetransfer.com",
   "Picnic|picnic.app", "Docker|docker.com", "Takeaway.com|justeattakeaway.com", "Flexport|flexport.com", "Plaid|plaid.com", "Reddit|redditinc.com", "T-Mobile|t-mobile.nl", "KPN|kpn.com", "MediaMarkt|mediamarkt.nl", "bunq|bunq.com",
   "Tiqets|tiqets.com", "Adevinta|adevinta.com", "eBay|ebay.com", "ASML|asml.com", "bol.com|bol.com", "ING|ing.com", "Rabobank|rabobank.com", "ABN AMRO|abnamro.com", "Albert Heijn|ah.nl", "Salesforce|salesforce.com", "Oracle|oracle.com",
   "Atlassian|atlassian.com", "Datadog|datadoghq.com", "Cloudflare|cloudflare.com", "Snowflake|snowflake.com", "MongoDB|mongodb.com", "Slack", "Zoom", "Cisco|cisco.com", "Intel|intel.com", "NVIDIA|nvidia.com", "IBM|ibm.com", "SAP|sap.com",
   "Shopify|shopify.com", "Airbnb|airbnb.com", "LinkedIn|linkedin.com", "Tesla|tesla.com", "Dropbox|dropbox.com", "Pinterest|pinterest.com", "Snap|snap.com", "TikTok|tiktok.com", "Canva|canva.com", "Figma|figma.com", "Notion|notion.so", "OpenAI|openai.com", "Anthropic|anthropic.com"]),
}
def parse(entry):
    name, _, dom = entry.partition("|")
    return name.strip(), (f"https://www.{dom.strip()}" if dom else None)
def all_companies():
    seen, out = set(), []
    for k, (_, lst) in C.items():
        for e in lst:
            n, w = parse(e)
            if n.lower() in seen: continue
            seen.add(n.lower()); out.append((n, w, k))
    return out
def clusters_for(query):
    """cluster keys whose keyword list or name matches the search words"""
    import re
    words = set(re.findall(r"[a-z0-9.+#]+", query.lower())) - {"developer", "engineer", "jobs", "job", "senior", "junior", "intern", "internship", "stage", "engineering", "manager", "specialist", "software"}
    hits = []
    for k, (kws, _) in C.items():
        kw = set(kws.split())
        score = len(words & kw) + (2 if k in words else 0)
        if score: hits.append((score, k))
    return [k for _, k in sorted(hits, reverse=True)]
