cd ~/EDAN/backend && mkdir -p scripts && cat > scripts/fix-mobile-engine.py <<'PY'
from pathlib import Path
from datetime import datetime
import subprocess
import sys
import re
import shutil

ROOT = Path.cwd()
BACKUP = ROOT / ".backups" / ("mobile-engine-" + datetime.now().strftime("%Y%m%d-%H%M%S"))

FILES = [
    "src/generator/full/mobilePageGenerator.ts",
    "src/generator/full/mobileNavigationFileGenerator.ts",
    "src/generator/full/mobileNavigationGenerator.ts",
    "src/generator/runtime.ts",
]

originals = {}
changed = []

def read(rel):
    p = ROOT / rel
    if not p.is_file():
        raise RuntimeError(f"Fichier indispensable absent : {rel}")
    return p.read_text(encoding="utf-8")

def write(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    if rel not in changed:
        changed.append(rel)

def run(cmd):
    print("\n>>>", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode

try:
    print("=== 1. VERIFICATION DES FICHIERS ===", flush=True)
    for rel in FILES:
        originals[rel] = read(rel)

    # Refuser d'écraser une version différente de celle attendue.
    runtime = originals["src/generator/runtime.ts"]
    if "export function createRuntime" not in runtime:
        raise RuntimeError("Structure inattendue de runtime.ts ; aucune modification effectuée.")

    mobile_page = r'''import type {FullStackContract} from "./fullStackContract.js";

function normalizeDartIdentifier(value:string):string {
  const normalized = value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return normalized || "page";
}

function className(value:string):string {
  return normalizeDartIdentifier(value)
    .split("_")
    .filter(Boolean)
    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
    .join("") + "Screen";
}

function dartString(value:string):string {
  // JSON fournit un littéral échappé ; le dollar doit aussi être neutralisé
  // pour éviter l'interpolation involontaire dans une chaîne Dart.
  return JSON.stringify(value).replace(/\$/g, "\\$");
}

function semantic(value:string):string {
  return value.normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function routeForPage(page:string):string {
  return "/" + semantic(page).replace(/\s+/g, "-");
}

function findRoute(input:FullStackContract, action:string) {
  const target = semantic(action);
  const candidates = input.apiRoutes.filter(route => {
    const routeAction = semantic(route.action || "");
    return routeAction && (
      routeAction === target ||
      routeAction.includes(target) ||
      target.includes(routeAction)
    );
  });
  if (candidates.length === 1) return candidates[0];

  const scored = input.apiRoutes.map(route => {
    const context = semantic([
      route.action || "", route.purpose || "", route.feature || "",
      route.entity || "", route.path || ""
    ].join(" "));
    const words = target.split(" ").filter(word => word.length > 2);
    return {route, score: words.filter(word => context.includes(word)).length};
  }).filter(item => item.score > 0)
    .sort((a,b) => b.score-a.score);

  if (scored.length && (scored.length === 1 || scored[0].score > scored[1].score)) {
    return scored[0].route;
  }
  return undefined;
}

function componentLabel(component:any):string {
  const props = component?.props || {};
  return String(props.label || props.title || props.text || props.placeholder ||
    component?.name || component?.type || "Composant");
}

export function generateMobilePageFiles(input:FullStackContract) {
  const files:Record<string,string> = {};
  const pages = [...new Set(input.pages.length ? input.pages : ["Accueil"])];
  const seen = new Map<string,string>();

  for (const page of pages) {
    const safe = normalizeDartIdentifier(page);
    const prior = seen.get(safe);
    if (prior && prior !== page) {
      throw new Error(
        `Collision de noms d'écrans mobiles : "${prior}" et "${page}" -> "${safe}".`
      );
    }
    seen.set(safe, page);
  }

  for (const page of pages) {
    const safe = normalizeDartIdentifier(page);
    const widget = className(page);
    const screen = input.screenPlan.find(s => semantic(s.name) === semantic(page));
    const uiPage = input.uiux.pages.find(p => semantic(p.name) === semantic(page));
    const fields = [...new Set((screen?.fields || []).map(String).filter(Boolean))];
    const actions = [...new Set((screen?.actions || []).map(String).filter(Boolean))];

    const fieldWidgets = fields.map(field => `
            TextFormField(
              controller: _controllers.putIfAbsent(
                ${dartString(field)}, () => TextEditingController(),
              ),
              decoration: InputDecoration(
                labelText: ${dartString(field)},
                border: const OutlineInputBorder(),
              ),
            ),`).join("\n");

    const sections = (uiPage?.sections || []).map(section => {
      const children = (section.components || []).map((component:any) => `
            Card(
              child: ListTile(
                title: Text(${dartString(componentLabel(component))}),
              ),
            ),`).join("\n");
      return `
          if (${JSON.stringify(Boolean(section.name))}) ...[
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 8),
              child: Text(
                ${dartString(section.name || "")},
                style: Theme.of(context).textTheme.titleMedium,
              ),
            ),
            ${children || "const SizedBox.shrink(),"}
          ],`;
    }).join("\n");

    const actionWidgets = actions.map(action => {
      const route = findRoute(input, action);
      const nav = /^(ouvrir|aller|naviguer|accéder|revenir|retour)\b/i.test(action.trim());
      const targetPage = nav
        ? pages.find(candidate => candidate !== page &&
            semantic(action).includes(semantic(candidate)))
        : undefined;

      let callback:string;
      if (targetPage) {
        callback = `Navigator.pushNamed(context, ${dartString(routeForPage(targetPage))});`;
      } else if (route) {
        const method = String(route.method || "GET").toUpperCase();
        callback = `await _executeAction(
                  context,
                  ${dartString(method)},
                  ${dartString(route.path)},
                  ${dartString(action)},
                  _controllers.map((key, value) => MapEntry(key, value.text)),
                );`;
      } else {
        callback = `ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(
                    ${dartString('Action non configurée : ' + action)}
                  )),
                );`;
      }

      return `
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () async { ${callback} },
                  child: Text(${dartString(action)}),
                ),
              ),
            ),`;
    }).join("\n");

    files[`lib/screens/${safe}_screen.dart`] = `import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

const String _edanApiBaseUrl = String.fromEnvironment(
  'EDAN_API_BASE_URL',
  defaultValue: 'http://10.0.2.2:4000',
);

class ${widget} extends StatefulWidget {
  const ${widget}({super.key});

  @override
  State<${widget}> createState() => _${widget}State();
}

class _${widget}State extends State<${widget}> {
  final Map<String, TextEditingController> _controllers = {};

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _executeAction(
    BuildContext context,
    String method,
    String path,
    String actionName,
    Map<String, String> payload,
  ) async {
    try {
      final uri = Uri.parse('$_edanApiBaseUrl$path');
      final request = http.Request(method, uri);
      request.headers['Accept'] = 'application/json';

      if (!{'GET', 'HEAD', 'DELETE', 'OPTIONS'}.contains(method)) {
        request.headers['Content-Type'] = 'application/json';
        request.body = jsonEncode(payload);
      }

      final streamed = await http.Client().send(request);
      final response = await http.Response.fromStream(streamed);
      if (!context.mounted) return;

      final message = response.statusCode >= 200 && response.statusCode < 300
        ? '$actionName : opération réussie'
        : '$actionName : erreur HTTP \${response.statusCode}';

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
      );
    } catch (error) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Erreur réseau : $error')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(${dartString(page)})),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          ${sections}
          ${fieldWidgets}
          ${actionWidgets}
          if (${fields.length === 0 && actions.length === 0})
            const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('Aucune action métier définie pour cet écran.'),
              ),
            ),
        ],
      ),
    );
  }
}
`;
  }
  return files;
}
'''

    navigation_file = r'''function dartString(value:string):string {
  return JSON.stringify(value).replace(/\$/g, "\\$");
}

export function generateMobileNavigationFile(
  navigation:Array<{name:string;index:number;route:string}>
) {
  const items = navigation.map(item => `          ListTile(
            leading: const Icon(Icons.chevron_right),
            title: Text(${dartString(item.name)}),
            onTap: () => Navigator.pushNamed(
              context, ${dartString(item.route)},
            ),
          ),`).join("\n");

  return `import 'package:flutter/material.dart';

class EdanNavigation extends StatelessWidget {
  const EdanNavigation({super.key});

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
${items}
      ],
    );
  }
}
`;
}
'''

    navigation_generator = r'''import type {FullStackContract} from "./fullStackContract.js";

function normalizeRoute(value:string):string {
  return value.normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "page";
}

export function generateMobileNavigation(input:FullStackContract) {
  const pages = [...new Set(input.pages.length ? input.pages : ["Accueil"])];
  const seen = new Map<string,string>();

  const navigation = pages.map((page,index) => {
    const route = "/" + normalizeRoute(page);
    const prior = seen.get(route);
    if (prior && prior !== page) {
      throw new Error(
        `Collision de route mobile : "${prior}" et "${page}" -> "${route}".`
      );
    }
    seen.set(route,page);
    return {name:page,index,route};
  });

  return navigation;
}
'''

    print("=== 2. SAUVEGARDE ===", flush=True)
    BACKUP.mkdir(parents=True, exist_ok=True)
    for rel in FILES:
        destination = BACKUP / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, destination)

    print("Sauvegardes :", BACKUP, flush=True)

    print("=== 3. APPLICATION DES CORRECTIONS ===", flush=True)
    write("src/generator/full/mobilePageGenerator.ts", mobile_page)
    write("src/generator/full/mobileNavigationFileGenerator.ts", navigation_file)
    write("src/generator/full/mobileNavigationGenerator.ts", navigation_generator)

    runtime = originals["src/generator/runtime.ts"]
    fixed_runtime = runtime.replace(
        r'.replace(/\\s+/g,"-")',
        r'.replace(/\s+/g,"-")'
    )
    fixed_runtime = fixed_runtime.replace(
        "pages:pages.map((name,index)=>({",
        '(pages.length ? pages : ["Accueil"]).map((name,index)=>({'
    )
    if fixed_runtime == runtime:
        print("AVERTISSEMENT : aucun motif runtime.ts correspondant ; fichier conservé.", flush=True)
    else:
        write("src/generator/runtime.ts", fixed_runtime)

    print("=== 4. VERIFICATION TYPESCRIPT ===", flush=True)
    if run(["npx", "tsc", "--noEmit"]) != 0:
        raise RuntimeError("Échec de TypeScript.")

    print("=== 5. TESTS FONCTIONNELS MOBILES ===", flush=True)
    test_file = ROOT / ".tmp-mobile-engine-regression.ts"
    test_file.write_text(r'''
import {generateMobilePageFiles} from "./src/generator/full/mobilePageGenerator.js";
import {generateMobileNavigation} from "./src/generator/full/mobileNavigationGenerator.js";
import {generateMobileNavigationFile} from "./src/generator/full/mobileNavigationFileGenerator.js";
import type {FullStackContract} from "./src/generator/full/fullStackContract.js";

const contract = {
  projectId: "mobile-regression",
  name: "Application test",
  idea: "Gestion des élèves",
  pages: ["Élèves", "Paiements"],
  screenPlan: [
    {name:"Élèves", fields:["Nom","Classe"], actions:["Créer un élève"], entities:["Élève"]},
    {name:"Paiements", fields:["Montant"], actions:["Enregistrer le paiement"], entities:["Paiement"]}
  ],
  apiRoutes: [
    {method:"POST",path:"/api/eleves",action:"Créer un élève",purpose:"Créer un élève"},
    {method:"POST",path:"/api/paiements",action:"Enregistrer le paiement",purpose:"Enregistrer un paiement"}
  ],
  uiux: {
    pages: [
      {name:"Élèves",layout:"stack",components:[],sections:[
        {name:"Informations",components:[{type:"text",name:"Nom de l'élève",props:{label:"Nom de l'élève"}}]}
      ]},
      {name:"Paiements",layout:"stack",components:[],sections:[]}
    ],
    theme:{mode:"light",primary:"#123456",secondary:"#654321",borderRadius:"8"},
    designSystem:{},
    navigation:[],
    responsive:true
  },
  actions:["Créer un élève","Enregistrer le paiement"],
  features:[],
  databaseEntities:[],
  databaseRelations:[],
  relations:[],
  integrations:[],
  workflows:[]
} as unknown as FullStackContract;

const pages = generateMobilePageFiles(contract);
if (!pages["lib/screens/eleves_screen.dart"]?.includes("Créer un élève")) {
  throw new Error("L'action métier n'est pas générée sur l'écran Élèves.");
}
if (!pages["lib/screens/eleves_screen.dart"]?.includes("/api/eleves")) {
  throw new Error("La route API de création d'élève n'est pas liée au bouton.");
}
if (!pages["lib/screens/eleves_screen.dart"]?.includes("TextFormField")) {
  throw new Error("Les champs métier ne sont pas générés.");
}
const navigation = generateMobileNavigation(contract);
if (navigation[0].route !== "/eleves") throw new Error("Route accentuée incorrecte.");
const navSource = generateMobileNavigationFile(navigation);
if (!navSource.includes("onTap") || !navSource.includes("/eleves")) {
  throw new Error("La navigation ne déclenche pas de transition.");
}
let collisionDetected = false;
try {
  generateMobileNavigation({...contract,pages:["Élèves","Eleves"]});
} catch {
  collisionDetected = true;
}
if (!collisionDetected) throw new Error("Collision de routes non détectée.");
console.log("PASS : écrans, champs, actions API, navigation et collisions.");
''', encoding="utf-8")

    try:
        if run(["npx", "tsx", ".tmp-mobile-engine-regression.ts"]) != 0:
            raise RuntimeError("Échec des tests fonctionnels mobiles.")
    finally:
        test_file.unlink(missing_ok=True)

    print("\nCORRECTIONS APPLIQUEES ET VERIFIEES.", flush=True)
    print("Fichiers modifiés :", *changed, sep="\n- ")
    print("Sauvegardes :", BACKUP)
    print("Attention : les tests Dart/Flutter réels exigent le SDK Flutter.", flush=True)

except Exception as exc:
    print("\nECHEC :", exc, flush=True)
    print("Restauration des fichiers modifiés...", flush=True)
    for rel in reversed(changed):
        if rel in originals:
            (ROOT / rel).write_text(originals[rel], encoding="utf-8")
            print("Restauré :", rel)
    print("Les sauvegardes éventuelles restent disponibles dans :", BACKUP, flush=True)
    sys.exit(1)
PY
python3 scripts/fix-mobile-engine.py