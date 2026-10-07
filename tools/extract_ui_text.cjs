/** Parse JSX/TypeScript instead of matching strings across JSX tag boundaries. */
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../dashboard/node_modules/typescript');
const files = JSON.parse(fs.readFileSync(0, 'utf8'));
const fields = /^(placeholder|title|aria-label|alt|label|name|text|hint|description|error|heading|caption|message|emptyText|empty|confirmLabel|cancelLabel|saveLabel|tooltip)$/;
const out = [];
for (const [file, rel] of files) {
  const source = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
  function visit(node) {
    if (ts.isJsxElement(node)) {
      const tag = node.openingElement.tagName.getText(source);
      if (["style", "script", "code", "pre"].includes(tag)) return;
      if (node.openingElement.attributes.properties.some(attr => ts.isJsxAttribute(attr) && attr.name.getText(source) === "data-no-translate")) return;
    }
    if (ts.isJsxText(node)) out.push([node.text, rel, true]);
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) {
      const parent = node.parent;
      const attribute = ts.isJsxAttribute(parent) && fields.test(parent.name.getText(source));
      const property = ts.isPropertyAssignment(parent) && fields.test(parent.name.getText(source).replace(/^['"]|['"]$/g, ''));
      const jsx = ts.isJsxExpression(parent);
      const dialog = ts.isCallExpression(parent) && /(?:toast\.|localizedConfirm|localizedPrompt|localizedAlert|confirm|prompt|alert)/.test(parent.expression.getText(source));
      if (!ts.isImportDeclaration(parent) && !ts.isImportSpecifier(parent)) {
        out.push([node.text, rel, attribute || property || jsx || dialog || /^[A-ZÄÖÜ][a-zäöüß]+$/.test(node.text)]);
      }
    }
    if (ts.isTemplateExpression(node)) {
      let number = 0;
      function alternatives(expression) {
        if (ts.isParenthesizedExpression(expression)) return alternatives(expression.expression);
        if (ts.isConditionalExpression(expression)) return [...alternatives(expression.whenTrue), ...alternatives(expression.whenFalse)];
        if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) return [expression.text];
        if (ts.isTemplateExpression(expression)) return templates(expression);
        return [`{${++number}}`];
      }
      function templates(template) {
        let values = [template.head.text];
        for (const span of template.templateSpans) {
          const choices = alternatives(span.expression);
          values = values.flatMap(value => choices.map(choice => value + choice + span.literal.text));
        }
        return values;
      }
      const parent = node.parent;
      const attribute = ts.isJsxExpression(parent) && ts.isJsxAttribute(parent.parent);
      const visible = attribute ? fields.test(parent.parent.name.getText(source))
        : ts.isJsxExpression(parent)
        || ts.isPropertyAssignment(parent) && fields.test(parent.name.getText(source))
        || ts.isCallExpression(parent) && /(?:toast\.|localizedConfirm|localizedPrompt|localizedAlert|confirm|prompt|alert)/.test(parent.expression.getText(source));
      for (const value of templates(node)) {
        const numbers = new Map();
        const sequential = value.replace(/\{(\d+)\}/g, (token, number) => {
          if (!numbers.has(number)) numbers.set(number, numbers.size + 1);
          return `{${numbers.get(number)}}`;
        });
        out.push([sequential, rel, visible]);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(source);
}
process.stdout.write(JSON.stringify(out));
