// ESLint supplies the repository's TypeScript checker, including Svelte templates.
const operators = new Set(["==", "!=", "===", "!==", "<", "<=", ">", ">=", "+", "-", "*", "/", "%", "**", "|", "&", "^", "<<", ">>", ">>>"]);

export default {
  rules: {
    "value-semantics": {
      meta: {
        type: "problem",
        docs: { description: "Require value methods for configured immutable value objects." },
        schema: [{
          type: "object",
          properties: {
            types: {
              type: "array",
              minItems: 1,
              items: {
                type: "object",
                properties: { name: { type: "string" }, source: { type: "string" } },
                required: ["name", "source"],
                additionalProperties: false,
              },
            },
          },
          required: ["types"],
          additionalProperties: false,
        }],
        messages: {
          operator: "{{name}} requires its value comparison/arithmetic methods; {{operation}} coerces or compares object identity.",
          identity: "{{name}} requires value keys or value comparisons; {{operation}} uses object identity.",
          sort: "{{name}} requires an explicit value comparator; default sort orders strings.",
        },
      },
      create(context) {
        const services = context.sourceCode.parserServices;
        if (!services?.program || !services.esTreeNodeToTSNodeMap) {
          throw new Error("value-semantics requires TypeScript parser services with projectService enabled");
        }
        const checker = services.program.getTypeChecker();
        const owners = context.options[0]?.types ?? [];
        const typeOf = (node) => checker.getTypeAtLocation(services.esTreeNodeToTSNodeMap.get(node));
        const nullish = (node) => ["null", "undefined"].includes(checker.typeToString(typeOf(node)));
        function owner(type) {
          if (type.isUnionOrIntersection()) {
            return type.types.map(owner).find(Boolean);
          }
          const symbol = type.getSymbol();
          return owners.find((candidate) =>
            symbol?.getName() === candidate.name &&
            symbol.getDeclarations()?.some((declaration) =>
              declaration.getSourceFile().fileName.replaceAll("\\", "/").endsWith("/" + candidate.source),
            ),
          );
        }
        function report(node, operands, messageId, operation) {
          const found = operands.filter(Boolean).map((operand) => owner(typeOf(operand))).find(Boolean);
          if (found) context.report({ node, messageId, data: { name: found.name, operation } });
        }
        function builtin(type, names) {
          const symbol = type.getSymbol();
          return names.includes(symbol?.getName()) && symbol.getDeclarations()?.some((declaration) =>
            /\/lib\.[^/]+\.d\.ts$/.test(declaration.getSourceFile().fileName),
          );
        }
        function keyOwner(type) {
          return checker.getTypeArguments(type).map(owner)[0];
        }
        return {
          BinaryExpression(node) {
            if (!operators.has(node.operator)) return;
            if (["==", "!=", "===", "!=="].includes(node.operator) &&
                (nullish(node.left) || nullish(node.right))) return;
            report(node, [node.left, node.right], "operator", node.operator);
          },
          AssignmentExpression(node) {
            if (node.operator !== "=") report(node, [node.left, node.right], "operator", node.operator);
          },
          UnaryExpression(node) {
            if (["+", "-", "~"].includes(node.operator)) report(node, [node.argument], "operator", node.operator);
          },
          UpdateExpression(node) {
            report(node, [node.argument], "operator", node.operator);
          },
          NewExpression(node) {
            const type = typeOf(node);
            if (!builtin(type, ["Map", "Set", "WeakMap", "WeakSet"])) return;
            const found = keyOwner(type);
            if (found) context.report({ node, messageId: "identity", data: { name: found.name, operation: type.getSymbol().getName() } });
          },
          CallExpression(node) {
            const member = node.callee;
            if (member.type !== "MemberExpression") return;
            const method = member.computed ? member.property.value : member.property.name;
            const receiver = typeOf(member.object);
            if (builtin(receiver, ["Array", "ReadonlyArray"])) {
              if (["includes", "indexOf", "lastIndexOf"].includes(method)) {
                report(node, [node.arguments[0]], "identity", method);
              }
              if (["sort", "toSorted"].includes(method) && node.arguments.length === 0) {
                const found = keyOwner(receiver);
                if (found) context.report({ node, messageId: "sort", data: { name: found.name } });
              }
            }
            if (builtin(receiver, ["Map", "Set", "WeakMap", "WeakSet", "ReadonlyMap", "ReadonlySet"]) &&
                ["get", "set", "add", "has", "delete"].includes(method)) {
              report(node, [node.arguments[0]], "identity", method);
            }
            if (builtin(receiver, ["ObjectConstructor"]) && method === "is") {
              report(node, node.arguments, "identity", "Object.is");
            }
          },
        };
      },
    },
  },
};
