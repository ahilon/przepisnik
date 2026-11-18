# Demo content provenance

The current six sample recipe texts and ingredient quantities were authored with
AI assistance for this project on 2026-11-17. They are demonstration content, not
extractions from personal diet-plan PDFs or website recipe descriptions. Generic
dish categories and existing recipe IDs were retained for application compatibility.

The six `recipes/<id>/image.png` files were newly generated with the built-in
`image_gen` tool on the same date. No photographs or other reference images were
supplied to generation. The images are illustrations of the sample dishes, not
photographs of meals cooked and tested from these quantities. There are no external
photo credits to carry over from the replaced images. This record documents how
these assets were made; it does not establish a software license for the project.

Nutrition is unset (`null`): values from the replaced recipes would not describe
these new ingredients. Portion labels are UI examples, not dietary advice. The
unchanged `placeholder.png` is a plain solid-colour fallback, not a food photograph.

This replacement changes the current files only. Previous demo text and images
remain in existing Git commits, old workflow artifacts/images and previously seeded
Docker volumes until those are separately addressed. A new commit alone does not
remove the old assets from Git history. See [demo setup](README.md) before resetting
a disposable demo volume; never reset a real instance's data to refresh examples.

## Image prompts

Each prompt produced one separate image; no edits of the old images were used.

### `recipes/azjatycka-zupa-z-makaronem/image.png`

```text
Use case: photorealistic food photograph. Asset type: square recipe-card image for a Polish recipe app demo. Generate a brand-new original image, with no input or reference image. Subject: a steaming bowl of mild coconut noodle soup with thin rice noodles, golden tofu cubes, orange carrot ribbons, sliced mushrooms, green pak choi leaves and a lime wedge. Scene: simple ivory ceramic bowl on a pale wooden kitchen table, natural soft window light, appetizing realistic food textures, three-quarter overhead view, dish centered and fully visible. No meat, no branding, no text, no collage, no watermark. Only one finished dish. Save the generated image as a local file if supported and report its path.
```

### `recipes/bajgiel-z-domowym-twarozkiem/image.png`

```text
Use case: photorealistic food photograph. Asset type: square recipe-card image for a Polish recipe app demo. Generate a brand-new original image with no input or reference images. Subject: A sliced sesame bagel with a generous filling of creamy white cottage cheese mixed with chopped chives, thin red radish rounds, cucumber slices and baby spinach. Two halves on a small matte cream plate. One finished breakfast serving. Scene: pale wooden kitchen table, natural soft window light, realistic appetizing textures. Three-quarter overhead view with the entire dish centered and visible. No branding, text, collage or watermark. No additional dishes.
```

### `recipes/bataty-z-pieczonymi-warzywami-i-serem-typu-feta/image.png`

```text
Use case: photorealistic food photograph. Asset type: square recipe-card image for a Polish recipe app demo. Generate a brand-new original image with no input or reference images. Subject: A rustic cream ceramic plate of roasted orange sweet potato chunks with golden chickpeas, red bell pepper strips, zucchini half-moons, crumbled white feta and chopped parsley. Everything cooked and lightly browned, with a lemon wedge. One finished lunch serving. Scene: pale wooden kitchen table, natural soft window light, realistic appetizing textures. Three-quarter overhead view with the entire dish centered and visible. No branding, text, collage or watermark. No additional dishes.
```

### `recipes/budyniowa-owsianka-z-owocami/image.png`

```text
Use case: photorealistic food photograph. Asset type: square recipe-card image for a Polish recipe app demo. Generate a brand-new original image with no input or reference images. Subject: A bowl of creamy vanilla oatmeal topped with bright raspberries, sliced banana and a little chopped hazelnut. Oats clearly visible, no artificial dessert decorations. One breakfast bowl made with milk and cornstarch, vanilla and a little maple syrup. Scene: pale wooden kitchen table, natural soft window light, realistic appetizing textures. Three-quarter overhead view with the entire dish centered and visible. No branding, text, collage or watermark. No additional dishes.
```

### `recipes/burgery-z-grilla/image.png`

```text
Use case: photorealistic food photograph. Asset type: square recipe-card image for a Polish recipe app demo. Generate a brand-new original image with no input or reference images. Subject: One homemade grilled beef burger in a toasted sesame bun, with a single beef patty, a melted slice of cheddar, green lettuce, red tomato slices, sliced pickles and a thin layer of yogurt-mustard sauce. Small ivory plate, no fries, no extra burgers, no skewers. Scene: pale wooden kitchen table, natural soft window light, realistic appetizing textures. Three-quarter overhead view with the entire dish centered and visible. No branding, text, collage or watermark. No additional dishes.
```

### `recipes/butter-chicken/image.png`

```text
Use case: photorealistic food photograph. Asset type: square recipe-card image for a Polish recipe app demo. Generate a brand-new original image with no input or reference images. Subject: a single shallow ivory bowl with chunks of cooked chicken breast in a creamy orange tomato sauce, accompanied by a neat portion of fluffy basmati rice. A small swirl of cream and fresh cilantro on the sauce. Homemade mild butter-style chicken; no bones, no naan or extra dishes. Scene: pale wooden kitchen table, soft natural window light, realistic appetizing textures. Three-quarter overhead view, centered dish fully visible. No branding, text, collage or watermark.
```
