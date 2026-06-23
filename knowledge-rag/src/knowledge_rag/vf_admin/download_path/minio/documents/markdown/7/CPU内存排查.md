## 1.1 导致 CPU100%的原因有哪些

1. 死循环或者过度递归

2.复杂的算法和计算:大规模的数据处理或者大规模的计算操作

3.频繁的IO操作

4. 内存问题: 内存占用过高导致频繁垃圾回收，增加 CPU 负担

5. 线程问题: 死锁阻塞导致 CPU 占用过高

## 1.2 排查

1. ps -ef|grep java 查看 java 进程(第三列为进程 id) 或者

java 命令 jps (https://zhuanlan.zhihu.com/p/475571604?utm\_id=0)

2. top 命令查看比较耗费内存的进程(关注 PID %CPU %MEM 三列) 看看占用 CPU 或者内存最多的是不是咱们 java 应用进程的 PID(基本就是)

<table><tr><td>PID</td><td>USER</td><td>PR</td><td>NI</td><td>VIRT</td><td>RES</td><td>SHR</td><td>S</td><td>%CPU</td><td>%MEM</td><td>TIME+</td><td>COMMAND</td></tr><tr><td>1991</td><td>paralle+</td><td>20</td><td>0</td><td>462888</td><td>10692</td><td>5988</td><td>S</td><td>6.2</td><td>0.5</td><td>0:00.27</td><td>/usr/bin/ibus-daemon --panel di+</td></tr><tr><td>14680</td><td>paralle+</td><td>20</td><td>0</td><td>13140</td><td>3296</td><td>2696</td><td>R</td><td>6.2</td><td>0.2</td><td>0:00.01</td><td>top -c</td></tr><tr><td>1</td><td>root</td><td>20</td><td>0</td><td>167056</td><td>11196</td><td>7504</td><td>S</td><td>0.0</td><td>0.6</td><td>0:00.81</td><td>/sbin/init</td></tr><tr><td>2</td><td>root</td><td>20</td><td>0</td><td>0</td><td>0</td><td>0</td><td>S</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[kthreadd]</td></tr><tr><td>3</td><td>root</td><td>0</td><td>-20</td><td>0</td><td>0</td><td>0</td><td>I</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[rcu_gp]</td></tr><tr><td>4</td><td>root</td><td>0</td><td>-20</td><td>0</td><td>0</td><td>0</td><td>I</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[rcu_par_gp]</td></tr><tr><td>5</td><td>root</td><td>0</td><td>-20</td><td>0</td><td>0</td><td>0</td><td>I</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[netns]</td></tr><tr><td>7</td><td>root</td><td>0</td><td>-20</td><td>0</td><td>0</td><td>0</td><td>I</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[kworker/0:0H-events_highpri]</td></tr><tr><td>9</td><td>root</td><td>0</td><td>-20</td><td>0</td><td>0</td><td>0</td><td>I</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[mm_percpu_wq]</td></tr><tr><td>10</td><td>root</td><td>20</td><td>0</td><td>0</td><td>0</td><td>0</td><td>S</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[rcu_tasks_rude_]</td></tr><tr><td>11</td><td>root</td><td>20</td><td>0</td><td>0</td><td>0</td><td>0</td><td>S</td><td>0.0</td><td>0.0</td><td>0:00.00</td><td>[rcu_tasks_trace]</td></tr><tr><td>12</td><td>root</td><td>20</td><td>0</td><td>0</td><td>0</td><td>0</td><td>S</td><td>0.0</td><td>0.0</td><td>0:00.14</td><td>[ksoftirqd/0]</td></tr><tr><td>13</td><td>root</td><td>20</td><td>0</td><td>0</td><td>0</td><td>0</td><td>I</td><td>0.0</td><td>0.0</td><td>0:05.98</td><td>[rcu_sched]</td></tr><tr><td>14</td><td>root</td><td>rt</td><td>0</td><td>0</td><td>0</td><td>0</td><td>S</td><td>0.0</td><td>0.0</td><td>0:00.04</td><td>[migration/0]</td></tr></table>

3. top -H -p pid 观察占用 CPU 比较高的几个线程

<table><tr><td>PID</td><td>USER</td><td>PR</td><td>NI</td><td>VIRT</td><td>RES</td><td>SHR</td><td>S</td><td>%CPU</td><td>%MEM</td><td>TIME+</td><td>COMMAND</td></tr><tr><td>1888</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:14.02</td><td>gnome-shell</td></tr><tr><td>1903</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.01</td><td>gmain</td></tr><tr><td>1905</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:01.14</td><td>gdbus</td></tr><tr><td>1909</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.00</td><td>dconf worker</td></tr><tr><td>1910</td><td>paralle+</td><td>39</td><td>19</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.00</td><td>gnome-s:disk$0</td></tr><tr><td>1911</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.11</td><td>gnome-shell</td></tr><tr><td>1915</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.01</td><td>JS Helper</td></tr><tr><td>1916</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.06</td><td>JS Helper</td></tr><tr><td>2401</td><td>paralle+</td><td>20</td><td>0</td><td>3900076</td><td>240500</td><td>115768</td><td>S</td><td>0.0</td><td>11.9</td><td>0:00.00</td><td>threaded-ml</td></tr></table>

4. printf '%x\n' nid 十进制线程 id 转成 16 进制

5. jstack 进程 id > txt.log 输出线程堆栈信息 重点关注上面占用 CPU 或内存比较高的线程堆栈信息

```txt
1) 存在死锁:
线程状态 BLOCKED
"Thread-16" #60 daemon prio=5 os prio=31 tid=0x00007fa4760ed800 nid=0xbc03 waiting for monitor entry [0x00000030c9f8000]
java.lang.Thread.State: BLOCKED (on object monitor)
at com.rabbiter.bms.service.impl.BookInfoServiceImpl$2.run(BookInfoServiceImpl.java:109)
- waiting to lock <0x0000005c08b1748> (a java.lang.Integer)
- locked <0x0000005c08b1718> (a com.rabbiter.bms.model.BookInfo)
at java.lang.Thread.run(thread.java:750)

Locked owning synchronizers:
- None

"Thread-15" #59 daemon prio=5 os prio=31 tid=0x00007fa487188000 nid=0xfa03 waiting for monitor entry [0x00000030c8f5000]
java.lang.Thread.State: BLOCKED (on object monitor)
at com.rabbiter.bms.service.impl.BookInfoServiceImpl$1.run(BookInfoServiceImpl.java:94)
- waiting to lock <0x0000005c08b1718> (a com.rabbiter.bms.model.BookInfo)
- locked <0x0000005c08b1748> (a java.lang.Integer)
at java.lang.Thread.run(thread.java:750)

Locked owning synchronizers:
- None
```

## 文件最下面会打印 发现的死锁 deadlock

```txt
Found one Java-level deadlock:
"Thread-16":
    waiting to lock monitor 0x00007fa48716e8c8 (object 0x00000005c08b1748, a java.lang.Integer),
    which is held by "Thread-15"
"Thread-15":
    waiting to lock monitor 0x00007fa487a26df8 (object 0x00000005c08b1718, a com.rabbiter.bms.model.BookInfo),
    which is held by "Thread-16"
Java stack information for the threads listed above:
"Thread-16":
    at com.rabbiter.bms.service.impl.BookInfoServiceImpl$2.run(BookInfoServiceImpl.java:109)
    - waiting to lock <0x00000005c08b1748> (a java.lang.Integer)
    - locked <0x00000005c08b1718> (a com.rabbiter.bms.model.BookInfo)
    at java.lang.Thread.run(Thread.java:750)
"Thread-15":
    at com.rabbiter.bms.service.impl.BookInfoServiceImpl$1.run(BookInfoServiceImpl.java:94)
    - waiting to lock <0x00000005c08b1718> (a com.rabbiter.bms.model.BookInfo)
    - locked <0x00000005c08b1748> (a java.lang.Integer)
    at java.lang.Thread.run(Thread.java:750)
Found 1 deadlock.
```

## 2) 频繁 IO 操作暂定

应该能观察到 waiting on condition(等待资源) 进一步分析是在等待什么

## 3) 内存占用过高导致频繁 GC

此时 top -p -H 占用 CPU 过高的线程应该是 GC 线程 此时需要打印堆 dump 文件进一步分析频繁 GC 的原因

```csv
"VM Thread" os_prio=31 tid=0x00007fa48684e800 nid=0x5403 runnable
"GC task thread#0 (ParallelGC)" os_prio=31 tid=0x00007fa488809000 nid=0x2e4b runnable
"GC task thread#1 (ParallelGC)" os_prio=31 tid=0x00007fa488809800 nid=0x3e03 runnable
"GC task thread#2 (ParallelGC)" os_prio=31 tid=0x00007fa48680e800 nid=0x3003 runnable
"GC task thread#3 (ParallelGC)" os_prio=31 tid=0x00007fa48680f000 nid=0x3203 runnable
"GC task thread#4 (ParallelGC)" os_prio=31 tid=0x00007fa48680f800 nid=0x3b03 runnable
"GC task thread#5 (ParallelGC)" os_prio=31 tid=0x00007fa487011000 nid=0x3303 runnable
"GC task thread#6 (ParallelGC)" os_prio=31 tid=0x00007fa476009000 nid=0x3903 runnable
"GC task thread#7 (ParallelGC)" os_prio=31 tid=0x00007fa47600a000 nid=0x3503 runnable
"GC task thread#8 (ParallelGC)" os_prio=31 tid=0x00007fa47600a800 nid=0x3703 runnable
```

## 4) 等待获取监视器锁: waiting on monitor entry

## 暫定

```txt
1)模拟内存泄露:
    1 usage
    List<BookInfo> list = new ArrayList<>();
    1 usage - jiangwenchao *
    @Override
    public void whileTree() {
    while (true){
    BookInfo book = new BookInfo();
    list.add(book);
    }
}
2)报错信息如下:java.lang.OutOfMemoryError: Java heap space
java.lang.OutOfMemoryError Create breakpoint : Java heap space
at java.util.Arrays.copyOf(Arrays.java:3332) ~[na:1.8.0_341]
at java.lang.AbstractStringBuilder.ensureCapacityInternal(AbstractStringBuilder.java:124) ~[na:1.8.0_341]
at java.lang.AbstractStringBuilder.append(AbstractStringBuilder.java:448) ~[na:1.8.0_341]
at java.lang.StringBuilder.append(StringBuilder.java:142) ~[na:1.8.0_341]
at com.rabbiter.bms.service.impl.BookInfoServiceImplwhileTree(BookInfoServiceImpl.java:81) ~[classes/:na]
at com.rabbiter.bms.web.BookInfoController_whileTree(BookInfoController.java:70) ~[classes/:na] <14 internal lines>
at javax.servlet.httpophyservlet.service(HttpServlet.java:663) ~[tomcat-embed-core-9.0.31.jar:9.0.31] <1 internal line>
at javax.servlet.httpophyservlet.service(HttpServlet.java:741) ~[tomcat-embed-core-9.0.31.jar:9.0.31] <9 internal lines>
```

## 内存过高

## 1. 内存溢出报错

3)项目启动配置-XX:+HeapDumpOnOutOfMemoryError 打印 OOM 异常

或者 jmap -dump:format=b,file=/Users/jsir/programfiles/note/jvm/1.hprof 70467

3.1)配置了-XX:+HeapDumpOnOutOfMemoryError OOM的时候会保存当下的对转储文件通过线程转储看到哪个线程导致的OOM并且有堆栈信息

![](http://localhost:9000/knowledge-data/documents/images/7/images/639209d84e3922a7b29c7cf9ca0f9a6779ca21b88d57b37de28cf855aaa8fd9c.jpg)

## 当前对象集-类视图 可以看到 BookInfo 有很多实例 并且占据 196M 内存

<table><tr><td>名称</td><td>实例计数</td><td>大小</td></tr><tr><td>com.rabbit.bms.model.BookInfo</td><td>4,102,269</td><td>196 MB</td></tr><tr><td>char[]</td><td>34,823</td><td>3,301 KB</td></tr><tr><td>java.lang.String</td><td>34,754</td><td>834 KB</td></tr><tr><td>java.util.concurrent.ConcurrentHashMap$Node</td><td>23,028</td><td>736 KB</td></tr><tr><td>java.lang.Object</td><td>11,721</td><td>187 KB</td></tr><tr><td>java.lang.reflect.Method</td><td>10,414</td><td>916 KB</td></tr><tr><td>java.lang.Class</td><td>8,439</td><td>2,700 KB</td></tr><tr><td>java.lang.Class[]</td><td>7,056</td><td>63 KB</td></tr><tr><td>java.util.LinkedHashMap$Entry</td><td>7,005</td><td>280 KB</td></tr><tr><td>java.util.HashMap$Node</td><td>16,666</td><td>213 KB</td></tr><tr><td>java.lang.Object[]</td><td>16,481</td><td>16,799 KB</td></tr><tr><td>org.springframework.core.MethodClassKey</td><td>4,698</td><td>112 KB</td></tr><tr><td>org.springframework.core.ResolvableType</td><td>3,823</td><td>183 KB</td></tr><tr><td>int[]</td><td>3,505</td><td>168 KB</td></tr><tr><td>java.util.LinkedHashMap</td><td>3,211</td><td>179 KB</td></tr><tr><td>java.util.Linked incur$Node[]</td><td>2,820</td><td>253 KB</td></tr><tr><td>java.util.LinkedList$Node</td><td>2,560</td><td>61,440 字节</td></tr><tr><td>byte[]</td><td>2,018</td><td>372 KB</td></tr><tr><td>java.util.LinkedList</td><td>1,941</td><td>62,112 字节</td></tr><tr><td>java.util.concurrent.locks.ReentrantLock$NonfairSync</td><td>1,827</td><td>58,464 字节</td></tr><tr><td>java.util.ArrayList</td><td>1,816</td><td>43,584 字节</td></tr><tr><td>org.springframework.core.convert purter.GenericConverter$ConvertiblePair</td><td>1,794</td><td>43,056 字节</td></tr><tr><td>org.springframework.core.Resolvabletype[]</td><td>1,780</td><td>42,480 字节</td></tr><tr><td>org.springframework.core.convert.support.GenericConversionService$ConvertersForPair</td><td>1,445</td><td>23,120 字节</td></tr><tr><td>java.lang.invoke.MemberName</td><td>1,290</td><td>41,280 字节</td></tr><tr><td>java.lang.Integer</td><td>1,268</td><td>20,288 字节</td></tr><tr><td>org.springframework.util.concurrentReferenceHashMap$SoftEntryReference</td><td>1,264</td><td>60,672 字节</td></tr><tr><td>java.lang.String[]</td><td>1,226</td><td>46,992 字节</td></tr></table>

查看最大对象发现有个 Object[] 占用内存非常大(可能是存在一个 list 添加的元素过多猜测元素是 BookInfo)

![](http://localhost:9000/knowledge-data/documents/images/7/images/7c5ef1117f22a8bb34c7c1ff0e277889d559462525403a43c096bbe60e4b39e6.jpg)

查看 Object[] 传出引用：(跟猜测一致)

![](http://localhost:9000/knowledge-data/documents/images/7/images/dbf787cbc8a928d0d49527957f658404355a086929bc63abbdee3a2d7a7f8208.jpg)

结合线程转储视图(堆栈信息)定位的代码位置结合源码排查内存泄露的代码片段逻辑

3.2)如果是发生了OOM之后才进行jmap命令下载堆转储文件就没办法快照OOM那一刻的对内存了我们看下jmap的堆转储文件：

查看线程转储文件没发现问题:

![](http://localhost:9000/knowledge-data/documents/images/7/images/3dc3e109dea70b8c284a95ad2c48a115bf7fd3330edde56d3eaefd29d178cb1b.jpg)

查看类视图：(BookInfo 实例数量多 内存占用 180M)

![](http://localhost:9000/knowledge-data/documents/images/7/images/6364ab24e532ded22fcdab94eb1d4b0c713d74d3f4e3faaa75ba0c8637d19261.jpg)

查看最大对象视图：(ConcurrentHashMap 有一个实例占用 197M 内存 93%)

```txt
当前对象集：3,490个类的4,000,782个对象
1个选择步骤，该框大小(Shallow Size) 210 MB

不分组
树
使用...
在图表中显示
对象
java.util.concurrent.ConcurrentHashMap(0xa1ac6)
157 MB (100.0%) ladd java.util.concurrent.ConcurrentHashMap&Node[0x3c65a2]
196 MB (99.8%) [transitive reference] com.rabbiter.bms.service.impl.BookInfoServiceImpl(0xb7e59)
196 MB (99.8%) list java.util.ArrayList(0xb7e5a)
196 MB (99.8%) elementData java.lang.Object[0x3cd1ae]
另一个3,756,330实例，总保留大小为180 MB，最大单个保留大小为48 字节
呈一个201实例，总保留大小为82 MB，最大单个保留大小为116 MB
```

查看 ConcurrentHashMap 引用视图(传出引用)无法看出 concurrentHashMap 跟 BookInfo 的引

用关系

![](http://localhost:9000/knowledge-data/documents/images/7/images/4f23f744a82b3fb70aca52bb08454d81d8eb07ae8c894bee4dbcdba02dcf84dd.jpg)

可以通过 BookInfo 查看传入引用(可以看到 concurrentHashMap 跟 BookInfo 的引用关系)

![](http://localhost:9000/knowledge-data/documents/images/7/images/de8a80741e0bca1a61b782c35c9c8879d6493ec6ab82d601245168a706849673.jpg)

目前看无法定位出问题的代码位置，不过总和分析，BookInfo 存在很多对象,并且 GC 之后无法删除(因为 OOM 了对象还活着)根据引用暴露出来的关键业务类
BookInfoService->ArrayList->BookInfo 看看源代码能否分析出内存泄漏

## 2.元空间溢出报错

## 3.java.lang出自MemoryError:GC overhead limit

![](http://localhost:9000/knowledge-data/documents/images/7/images/a5a910ec2d360bb2dbd9294da81dafe71273c5998ac0e87e33abb979674bdd93.jpg)

如上图 GC 活动频繁且程序报错如下:

```txt
2024-04-07 17:13:30.973 INFO 18342 --- [nio-8092-exec-1] o.a.c.c.c.[.[localhost].[ /BookManager] : Initializing Spring DispatcherServlet 'dispatcherSer
2024-04-07 17:13:30.974 INFO 18342 --- [nio-8092-exec-1] o.s.web.servlet.DispatcherServlet : Initializing Servlet 'dispatcherServlet'
2024-04-07 17:13:31.924 INFO 18342 --- [nio-8092-exec-1] o.s.web.servlet.DispatcherServlet : Completed initialization in 49 ms
Exception in thread "http-nio-8092-exec-1" java.lang.OutOfMemoryError: GC overhead limit exceeded
JProfiler> Disconnected. Waiting for reconnection.
JProfiler> Listening on port: 51462.
Disconnected from the target VM, address: '127.0.0.1:51414', transport: 'socket'
Exception in thread "http-nio-8092-ClientPoller" java.lang.OutOfMemoryError: GC overhead limit exceeded
Exception in thread "SpringContextShutdownHook" java.lang.OutOfMemoryError: GC overhead limit exceeded
```

实例代码如下:

Map map = System.getProperties();

Random r = new Random();

while (true) {

$$
\begin{array}{l} \text { map.put(r.nextInt(),   "value"); } \\ \} \end{array}
$$

这个报错产生的原因是 98% 的时间用来做 GC 却只有不到 2% 的内存被回收，并内有产生 00M

Jprofile 分析堆转储文件：  
![](http://localhost:9000/knowledge-data/documents/images/7/images/c7eea2b864201925d02f0bbd8a77a14daf0cc9537958f3cf1b960e0ad45bd4d6.jpg)

可以看出肯定是存在内存泄露