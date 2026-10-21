1. 只用入参里的信息判断，没有依据的问题不要提；
2. result 是 {found, items}：items 每项是对象 {issue, modules, basis, type}：
   - issue：一句话说清问题；
   - modules：涉及的模块名，多个用逗号隔开；
   - basis：判断来源（需求哪一节、top.zs 哪个模块说明、目录里的哪一行）；
   - type：code=代码和约定不一致 / contract=约定有问题（职责重复、缺接口、缺函数、写法含糊、偏离需求，要改约定）/ req=需求有缺口或自相矛盾（要先改需求）。拿不准就写 contract；
3. 没有问题：found=否，items 为空数组；有问题：found=是，items 非空。found 和 items 必须一致。
