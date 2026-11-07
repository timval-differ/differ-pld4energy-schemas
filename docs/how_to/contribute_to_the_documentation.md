# Contribute to the documentation

The documentation is written in Markdown in `docs/` and built with
[MkDocs](https://www.mkdocs.org/) and the
[Material theme](https://squidfunk.github.io/mkdocs-material/). It is published
to GitHub Pages on every push to `main`
(`.github/workflows/mkdocs-deploy.yml`).

## Preview your changes

From the plugin folder (the docs tools are in the `dev` extras):

```sh
uv run --extra dev mkdocs serve -a 127.0.0.1:8001   # live preview; NOMAD uses port 8000
uv run --extra dev mkdocs build --strict   # fails on broken links, as a check
```

## Where things go

The pages follow the [Diátaxis](https://diataxis.fr/) structure: each kind of
page answers one kind of question. Put new content where its reader looks for
it.

| Page | Answers | Write |
| --- | --- | --- |
| [Tutorial](../tutorial/tutorial.md) | "How do I start?" | One complete first run, step by step, with no choices. |
| How-to guides (`docs/how_to/`) | "How do I do X?" | Instructions for one task each: [using the logbooks](use_this_plugin.md), [the dashboards](use_the_dashboard.md), [recipes](reuse_a_recipe.md), [installing](install_this_plugin.md), [contributing](contribute_to_this_plugin.md). |
| [Explanation](../explanation/explanation.md) | "Why is it like this?" | The reasons behind the data model, the read-only fields, the dashboards. |
| [Plugin structure](../explanation/plugin_structure.md) | "Where is what in the code?" | The map for developers: parts, flows, checks, tests, where to change things. |
| [Reference](../reference/references.md) | "What exactly is field X?" | Every section and field, with its unit and whether it can be edited. |

A new page must also be listed under `nav` in `mkdocs.yml`, and linked from the
[home page](../index.md) if readers should find it from there.

## Keep the docs in step with the code

Update the docs in the same pull request as the change:

| You changed | Update |
| --- | --- |
| A section or field of a schema | [Reference](../reference/references.md); the how-to guide that uses it |
| A field or behaviour of a dashboard | [Use the logbook dashboards](use_the_dashboard.md) |
| A module, endpoint, check, test file or CI job | [Plugin structure](../explanation/plugin_structure.md) |
| How to develop or test | [Contribute to this plugin](contribute_to_this_plugin.md) |
| A design decision | [Explanation](../explanation/explanation.md) |

## Style

- Write for the lab's users in the guides and for developers in the
  contributing guide and the plugin structure; say who a page is for when it
  is not obvious.
- Use the names the form shows (*Laser details*, *Process steps*) for users,
  and the code names (`LaserCalibration`, `steps`) for developers.
- Give units as the form shows them, and say when a value is stored in another
  unit (see [Units](../explanation/explanation.md#units)).
- Use admonitions for what readers must not miss:

    ```markdown
    !!! warning "Title"
        Text, indented by four spaces.
    ```

- Link to other pages with relative paths to their `.md` file, e.g.
  `[Reference](../reference/references.md)`; `mkdocs build --strict` reports
  links that do not resolve.
