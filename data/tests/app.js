const { createApp, ref, computed } = Vue;
const screens = [{"name": "文章编辑", "role": "表单"}, {"name": "文章列表", "role": "列表"}];
// 每个界面一份表单状态，按界面名索引。共用一个对象会让同名字段串味，
// 切界面也不会残留上一个界面填过的值。
const blank = {"文章编辑": {"status": "", "published_at": "", "featured": false, "title": "", "body": "", "slug": ""}, "文章列表": {}};

createApp({
  setup() {
    const route = ref(decodeURIComponent(location.hash.replace(/^#\/?/, "")) || screens[0].name);
    const forms = ref(JSON.parse(JSON.stringify(blank)));
    const rows = ref([{"title": "第一篇", "status": "published", "published_at": "2026-01-15"}, {"title": "草稿", "status": "draft", "published_at": ""}]);
    const current = computed(() => screens.find(s => s.name === route.value) || screens[0]);
    // 模板里统一写 form.xxx，指向当前界面那一份。
    const form = computed(() => forms.value[current.value.name] || {});
    function go(name) {
      route.value = name;
      location.hash = encodeURIComponent(name);
    }
    function reset(name) {
      forms.value[name] = JSON.parse(JSON.stringify(blank[name] || {}));
    }
    window.addEventListener("hashchange", () => {
      route.value = decodeURIComponent(location.hash.replace(/^#\/?/, "")) || screens[0].name;
    });
    // 骨架：这三个只打日志，接后端时替换成真正的请求。
    function onSubmit() { console.log("submit", current.value.name, form.value); }
    function onAction(name) { console.log("action", name, form.value); }
    function onRow(name, row) {
      console.log("row", name, row);
      if (name === "edit" && row) {
        const target = screens.find(s => s.role === "表单");
        if (target) {
          Object.assign(forms.value[target.name], row);
          go(target.name);
        }
      }
    }
    return { route, forms, form, rows, current, go, reset, onSubmit, onAction, onRow, screens };
  },
  template: `
    <nav>
      <a v-for="s in screens" :key="s.name"
         :class="{ active: current.name === s.name }"
         href="#" @click.prevent="go(s.name)">{{ s.name }}</a>
    </nav>
    <form v-if="current.name === '文章编辑'" class="screen" @submit.prevent="onSubmit">
      <section class="layout row">
  <section class="region col">
  <header class="region-h">侧栏</header>
  <section class="group col">
  <h3>发布设置</h3>
  <label class="field">
<span class="lbl">发布状态<span class="req">*</span></span>
<div class="radios"><label class="opt"><input type="radio" v-model="form.status" value="draft"> draft</label><label class="opt"><input type="radio" v-model="form.status" value="published"> published</label><label class="opt"><input type="radio" v-model="form.status" value="archived"> archived</label></div>
</label>

  <label class="field">
<span class="lbl">发布时间</span>
<input type="date" v-model="form.published_at">
</label>

  <label class="field">
<span class="lbl">是否推荐</span>
<input type="checkbox" v-model="form.featured">
</label>

</section>

</section>

  <section class="region col grow">
  <header class="region-h">主区</header>
  <section class="group grid">
  <h3>基本信息</h3>
  <label class="field">
<span class="lbl">标题<span class="req">*</span></span>
<input type="text" v-model="form.title" required>
</label>

  <label class="field">
<span class="lbl">正文内容</span>
<textarea v-model="form.body" rows="8"></textarea>
</label>

  <label class="field" v-if="form.featured">
<span class="lbl">短链</span>
<input type="text" v-model="form.slug">
</label>

</section>

  <button type="submit" class="btn btn-primary">保存</button>

  <button type="button" class="btn btn-danger" @click.prevent="onAction('delete')">删除</button>

</section>

</section>


    </form>
    <form v-if="current.name === '文章列表'" class="screen" @submit.prevent="onSubmit">
      <section class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>标题</th>
        <th>状态</th>
        <th>发布时间</th>
        <th></th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="(row, i) in rows" :key="i">
        <td>{{ row.title }}</td>
        <td>{{ row.status }}</td>
        <td>{{ row.published_at }}</td>
        <td class="row-acts">
          <button type="button" class="btn btn-ghost" @click="onRow('edit', row)">编辑</button>
        </td>
      </tr>
    </tbody>
  </table>
</section>

<p class="copy">点编辑跳回表单</p>


    </form>
  `
}).mount("#app");
