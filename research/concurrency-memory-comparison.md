# Concurrency And Memory Families

This note compares concurrency and memory models that are relevant to Zen's
actor/runtime direction.

The design question is:

```text
What should Zen copy, avoid, or adapt?
```

Representative examples are included to show the feel of each model. They are not
a promise that every snippet is exact current package API.

Document flow:

```text
1. State the Zen thesis.
2. Group languages by model family.
3. Walk each family with examples and takeaways.
4. Score the tradeoffs after the evidence.
5. Sketch a clean-room 10/10 reference API.
6. Turn that into the proposed Zen API shape.
```

## Thesis

Zen should not copy one language wholesale.

The strongest direction is:

```text
Hollywood actor API
+ BEAM/Pony actor isolation
+ Zig allocator discipline
+ Kotlin-style structured lifetimes
+ Nim write-once sync/async instinct
```

That points toward this user shape:

```zen
rt := std.concurrent.runtime
alloc := rt.async(1 << 20)
engine := actor_engine(alloc.addr())

room := engine.spawn(ChatRoom.new())
room.tell(.Join("alice"))
room.tell(.Say("alice", "hey"))
room.tell(.Stats)

engine.run()
engine.free()
alloc.free()
```

The public API should show allocator, engine, actor, and typed ref. It should not
show mailbox buffers, raw `receive` function pointers, primitive `yield`, or
runtime internals.

## Family Map

The families are not mutually exclusive. One language can expose multiple models,
and libraries can make one runtime feel like another.

The important split:

```text
Gleam and Erlang are in the same runtime family.
Go Hollywood and Erlang are in the same actor API family.
Go Hollywood is not in the BEAM/runtime family.
```

| Family | Members | Core Shape | Memory Story | Zen Takeaway |
|---|---|---|---|---|
| BEAM process / OTP | Erlang, Elixir, Gleam | Lightweight processes, mailboxes, supervisors | VM-owned per-process heaps and GC; messages usually copied | Steal supervision, mailboxes, process isolation, typed wrappers from Gleam |
| Actor libraries | Go Hollywood, Rust Actix, Akka-style systems | Engine/system spawns actors and routes messages | Host runtime memory; Go hides GC, Rust uses ownership | Steal beginner-friendly `engine.spawn(...).tell(...)` |
| Language-native isolated actors | Pony | Actor is a language primitive; mutable state is isolated | Per-actor heaps plus reference capabilities | Steal actor-owned state and send-safety, but avoid full capability complexity early |
| Structured coroutines | Kotlin coroutines, Swift tasks, Python `TaskGroup` | Scopes own tasks; cancellation propagates down the tree | Runtime-owned frames/stacks; usually no allocator API | Steal scoped lifetime and cancellation semantics |
| Promise / future async | TypeScript, Python asyncio, Rust async, Nim async, C# async | `async` functions return promise/future/task-shaped values | Heap/runtime allocation often implicit | Steal readable direct style, avoid function color |
| Generator / yield iteration | JavaScript generators, Python generators | Function frame can pause and resume as an iterator | Hidden suspended frame state | Keep for lazy iteration, not as a concurrency primitive |
| Sync/async codegen | Nim `multisync` | One source body generates sync and async variants | Program-level `--mm` choice is easy; not Zig-style per-call allocator capability | Steal write-once intent, avoid macro magic as the core model |
| Capability / allocator runtime | Zig `Allocator` + `Io`, Zen target | Caller passes allocator/runtime capability explicitly | Caller chooses heap, arena, pool, threaded/evented IO | This should be Zen's core composition model |
| Transactional memory | Haskell STM | Atomic composable transactions over shared variables | GC + immutable defaults | Steal composability for shared state, not as actor core |
| High-integrity tasking | Ada tasks and protected objects | Language-level tasks plus protected shared resources | Explicit, predictable systems style | Steal protected-state clarity; avoid heavy formal ceremony |
| Data engine / ECS | Bevy | App/world engine schedules systems over data | Engine owns storage layout and component memory | Steal app/engine ergonomics, not ECS for actors |

## BEAM / OTP Family

Members:

```text
Erlang
Elixir
Gleam
```

Core model:

```text
process owns state
process has mailbox
message send crosses process boundary
supervisor owns failure policy
runtime owns scheduling
runtime owns memory policy
```

### Erlang / Elixir

Erlang is the strongest production proof that lightweight processes, mailboxes,
and supervision can build reliable systems.

```erlang
chat_room(Online) ->
    receive
        {join, Name} ->
            io:format("joined ~p~n", [Name]),
            chat_room(Online + 1);
        {say, Text} ->
            io:format("message ~p~n", [Text]),
            chat_room(Online);
        stop ->
            ok
    end.

main() ->
    Room = spawn(fun() -> chat_room(0) end),
    Room ! {join, alice},
    Room ! {say, <<"hey">>},
    Room ! stop.
```

Good:

- Lightweight isolated processes.
- Per-process heaps and per-process GC reduce global pause problems.
- Supervision trees are a real answer to failure.
- Message passing is the normal model.

Bad:

- Dynamic messages make contracts weaker.
- Messages are usually copied.
- Memory layout and allocation policy are VM-owned.

### Gleam

Gleam is interesting because it keeps BEAM processes and OTP, but adds static
types and typed actor abstractions.

```gleam
import gleam/erlang/process
import gleam/otp/actor

pub type Msg {
  Join(String)
  Say(String)
  Stop
}

fn handle_message(online: Int, msg: Msg) -> actor.Next(Int, Msg) {
  case msg {
    Join(_name) -> actor.continue(online + 1)
    Say(_text) -> actor.continue(online)
    Stop -> actor.stop()
  }
}

pub fn main() {
  let assert Ok(started) =
    actor.new(0)
    |> actor.on_message(handle_message)
    |> actor.start

  let room = started.data
  process.send(room, Join("alice"))
  process.send(room, Say("hey"))
  process.send(room, Stop)
}
```

Zen takeaway:

```text
Steal typed actor messages and OTP-style wrappers.
Do not steal VM-owned memory policy.
```

## Actor Library Family

Members:

```text
Go Hollywood
Rust Actix
Akka-style systems
```

Core model:

```text
engine/system owns scheduling
actor owns mutable state
actor ref/address sends messages
library routes messages into receive/handler
```

### Go Hollywood

Go has excellent day-one concurrency ergonomics. Hollywood-style actor libraries
add the missing high-level structure: engine, spawn, send, receive.

```go
type ChatRoom struct {
	online int
}

func NewChatRoom() actor.Receiver {
	return &ChatRoom{}
}

func (c *ChatRoom) Receive(ctx *actor.Context) {
	switch msg := ctx.Message().(type) {
	case actor.Started:
		fmt.Println("chat room started")
	case Join:
		c.online++
		fmt.Println("joined", msg.Name)
	case Say:
		fmt.Println("message", msg.Text)
	}
}

func main() {
	engine := actor.NewEngine()
	room := engine.Spawn(NewChatRoom, "room")

	engine.Send(room, Join{Name: "alice"})
	engine.Send(room, Say{Text: "hey"})
}
```

Good:

- Actor setup feels like building a small app, not wiring primitives.
- The user does not manually pass `receive` around.
- Mailboxes, scheduling, and lifecycle are owned by the engine.
- This is the right feel for Zen's actor demo.

Bad:

- Go hides allocation and scheduling in the runtime.
- GC is not compatible with Zen's explicit allocator ethos.
- Raw goroutines/channels can become unstructured.

Zen takeaway:

```text
Steal the engine/spawn/tell ergonomics.
Do not steal hidden allocation or global runtime magic.
```

### Rust Actors

Rust does not have actors in the standard library, but frameworks such as Actix
show how typed actors can be layered over Rust's ownership system.

```rust
use actix::prelude::*;

struct ChatRoom {
    online: usize,
}

impl Actor for ChatRoom {
    type Context = Context<Self>;
}

#[derive(Message)]
#[rtype(result = "()")]
struct Join(String);

impl Handler<Join> for ChatRoom {
    type Result = ();

    fn handle(&mut self, msg: Join, _ctx: &mut Context<Self>) {
        self.online += 1;
        println!("joined {}", msg.0);
    }
}

#[actix::main]
async fn main() {
    let room = ChatRoom { online: 0 }.start();
    room.do_send(Join("alice".into()));
}
```

Zen takeaway:

```text
Steal typed actor messages and Send-style constraints.
Keep the public API closer to Hollywood than Actix.
```

## Language-Native Isolated Actors

Member:

```text
Pony
```

Pony is one of the strongest references because it joins actors and memory
safety. Actors own their state, communicate by messages, and the runtime uses
per-actor memory management.

```pony
actor ChatRoom
  var _online: USize = 0

  be join(name: String val) =>
    _online = _online + 1

  be say(text: String val) =>
    None

actor Main
  new create(env: Env) =>
    let room = ChatRoom
    room.join("alice")
    room.say("hey")
```

Good:

- Actor isolation is central, not bolted on.
- Per-actor heaps make memory ownership line up with concurrency ownership.
- Message passing is the normal way to cross isolation boundaries.
- Data-race freedom is part of the model.

Bad:

- The reference capability system is powerful but steep.
- Everything being actor-shaped can feel mandatory.
- It is a large semantic commitment.

Zen takeaway:

```text
Steal isolated actor state and allocator-per-actor thinking.
Avoid copying Pony's full capability lattice early.
```

## Structured Coroutine Family

Member:

```text
Kotlin coroutines
Swift tasks
Python asyncio TaskGroup
```

Kotlin is useful because it made structured concurrency mainstream: scopes own
coroutines, cancellation propagates, and task lifetimes are explicit.

```kotlin
suspend fun loadUser(id: String): User = coroutineScope {
    val profile = async { fetchProfile(id) }
    val settings = async { fetchSettings(id) }

    User(profile.await(), settings.await())
}

fun main() = runBlocking {
    val user = loadUser("alice")
    println(user)
}
```

Actor-ish channel shape:

```kotlin
sealed interface Msg {
    data class Join(val name: String) : Msg
    data class Say(val text: String) : Msg
}

fun CoroutineScope.chatRoom() = Channel<Msg>().also { inbox ->
    launch {
        var online = 0
        for (msg in inbox) {
            when (msg) {
                is Msg.Join -> online += 1
                is Msg.Say -> println(msg.text)
            }
        }
    }
}

fun main() = runBlocking {
    val room = chatRoom()
    room.send(Msg.Join("alice"))
    room.send(Msg.Say("hey"))
}
```

Good:

- Structured concurrency is a major ergonomic win.
- Cancellation propagates through coroutine hierarchies.
- Sequential-looking async code is friendly to ordinary developers.

Bad:

- `suspend` is still function color.
- Allocation and stack/frame mechanics are runtime-owned.
- Channels are useful but not the same as typed actor isolation.

Zen takeaway:

```text
Steal structured lifetime/cancellation thinking.
Do not steal suspend-colored function signatures.
```

### Swift

Swift is worth adding because it combines structured concurrency, `async`/`await`,
actors, and `Sendable` checks in a mainstream language.

Representative shape:

```swift
actor ChatRoom {
    var users: Set<String> = []

    func join(_ user: String) {
        users.insert(user)
    }

    func count() -> Int {
        users.count
    }
}

func main() async {
    let room = ChatRoom()
    await room.join("alice")
    let n = await room.count()
    print(n)
}
```

Zen takeaway:

```text
Steal actor-isolated state and Sendable-style checking.
Do not steal visible async/await coloring.
```

### Python Asyncio

Python belongs in the doc because it has both:

```text
generators/yield for iteration
asyncio/tasks/TaskGroup for concurrency
```

Representative asyncio shape:

```python
import asyncio

async def worker(name: str) -> None:
    await asyncio.sleep(1)
    print(name)

async def main() -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(worker("alice"))
        group.create_task(worker("bob"))

asyncio.run(main())
```

Zen takeaway:

```text
Steal TaskGroup-style structured lifetime.
Do not steal async def / await coloring.
```

## Promise / Future Async Family

Members:

```text
TypeScript / JavaScript async
Python asyncio
Rust async
Nim async
C# async
```

Core model:

```text
async marks a function
await marks a suspend point
function return type becomes promise/future-shaped
runtime/executor/event loop owns scheduling
```

### TypeScript / JavaScript

TypeScript async is the industry default because it is familiar and productive.

```ts
async function loadUser(id: string): Promise<User> {
  const response = await fetch(`/users/${id}`)
  return await response.json()
}

async function main() {
  const user = await loadUser("alice")
  console.log(user.name)
}
```

Zen takeaway:

```text
Steal readability.
Do not steal function color.
```

### JavaScript And Python Yield

JavaScript and Python both have `yield`, but it is generator/iterator machinery,
not the user-facing concurrency primitive Zen wants.

JavaScript:

```js
function* ids() {
  yield 1
  yield 2
}

for (const id of ids()) {
  console.log(id)
}
```

Python:

```python
def ids():
    yield 1
    yield 2

for id in ids():
    print(id)
```

These are useful for lazy streams. They are toxic as the main concurrency surface
because the user is manually exposing suspension points.

Zen takeaway:

```text
Keep yield-like mechanics inside iterators/generators or stdlib internals.
Do not expose yield as the actor/runtime primitive.
Prefer emit/send/message operations at the user layer.
```

### Rust Async

Rust is excellent at memory safety and static guarantees, but async exposes a lot
of machinery to users.

```rust
async fn load_user(client: &Client, id: UserId) -> Result<User> {
    let response = client.get(user_url(id)).send().await?;
    let user = response.json::<User>().await?;
    Ok(user)
}

#[tokio::main]
async fn main() -> Result<()> {
    let user = load_user(&client, UserId("alice")).await?;
    println!("{}", user.name);
    Ok(())
}
```

Actor-ish Rust often becomes channel plus task:

```rust
let (tx, mut rx) = tokio::sync::mpsc::channel::<ChatMsg>(64);

tokio::spawn(async move {
    let mut room = ChatRoom::new();
    while let Some(msg) = rx.recv().await {
        room.receive(msg);
    }
});

tx.send(ChatMsg::Join("alice".into())).await?;
```

Zen takeaway:

```text
Steal ownership, Send/Sync-style constraints, and typed boundaries.
Avoid exposing async machinery in function types.
```

## Rust Subfamilies

Rust is not one concurrency model. Rust is better understood as a safety substrate:

```text
ownership + borrowing + Send + Sync
```

Then different libraries build different concurrency models on top.

| Rust Model | Examples | Shape | Zen Relevance |
|---|---|---|---|
| OS threads / shared state | `std::thread`, `thread::scope`, `Arc`, `Mutex`, `RwLock`, atomics | Spawn real threads; share data only through thread-safe wrappers | Useful safety reference, but too low-level for the actor demo |
| Channels / CSP-ish messaging | `std::sync::mpsc`, Crossbeam, Flume, Tokio channels | Send values through channels between tasks/threads | Good typed message inspiration, but channels alone are not actors |
| Async runtime | Tokio, async-std, smol | Futures scheduled by executor; async IO, timers, tasks | Good production model, but exposes function color and executor machinery |
| Actor libraries | Actix, Ractor, xtra | Actors own state and receive typed messages | Good typed actor reference; API is usually heavier than Hollywood Go |
| Data parallelism | Rayon | Parallel iterators, fork/join, work-stealing | Excellent CPU parallelism model; not an actor model |
| ECS / app engine | Bevy | Engine schedules systems over data in a world | Good app ergonomics; not actor isolation |
| Embedded async | Embassy | Async tasks for embedded/no-std systems | Useful proof that async runtimes can be domain-specific capabilities |

The most important Rust idea for Zen is not `async`. It is the boundary rule:

```text
Only values that are safe to move/share may cross concurrency boundaries.
```

That maps well to a future Zen actor/message rule:

```zen
send<M: Send>(ref: ActorRef<M>, msg: M) bool
```

### Nim Async

Nim is interesting because `multisync` tries to avoid maintaining separate sync
and async versions of the same logic.

Nim also deserves real credit on memory UX: memory management is selectable by
compiler mode. Current Nim uses ORC by default, and the user can choose modes
such as `--mm:arc`, `--mm:orc`, `--mm:refc`, `--mm:markAndSweep`, `--mm:boehm`,
`--mm:go`, or `--mm:none`.

```nim
import asyncdispatch

proc fetchUserAsync(id: int): Future[string] {.async.} =
  let body = await httpGet("/users/" & $id)
  return body

proc fetchUserSync(id: int): string =
  waitFor fetchUserAsync(id)
```

Representative multisync-style shape:

```nim
# One body is transformed into sync/async variants by macro/pragmas.
proc readMany(client: Redis | AsyncRedis, count: int): Future[string] {.multisync.} =
  let first = await client.read()
  let rest = await client.read(count - 1)
  return first & rest
```

Zen takeaway:

```text
Steal "write once".
Steal easy memory-strategy selection.
Do not steal "generate a red async version".
Do not confuse program-level memory mode with Zig-style allocator passing.
```

### C# Async

C# is worth tracking because `Task`, `async`, and `await` are widely understood
and extremely practical for application code.

Representative shape:

```csharp
async Task<User> LoadUser(string id)
{
    var profile = await FetchProfile(id);
    var settings = await FetchSettings(id);
    return new User(profile, settings);
}
```

Zen takeaway:

```text
Steal "reads like direct code" ergonomics.
Do not steal Task-colored signatures as the core model.
```

## Capability Runtime Family

Members:

```text
Zig
Zen target
```

This is the most important family for Zen because it treats memory and runtime
behavior as explicit capabilities passed by the caller.

### Zig Memory

Zig is the best memory reference because allocation is explicit and ordinary.

```zig
const std = @import("std");

fn collect(allocator: std.mem.Allocator) !std.ArrayList(u8) {
    var list = std.ArrayList(u8).init(allocator);
    try list.append(42);
    return list;
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();

    const allocator = gpa.allocator();
    var list = try collect(allocator);
    defer list.deinit();
}
```

Memory feel:

```text
allocator is explicit
caller chooses strategy
containers do not hide heap policy
allocation failure is part of the type path
```

### Zig Concurrency

Zig's current concurrency direction is not "actors." It is closer to:

```text
pass an Io capability
let the application choose the Io implementation
make blocking/nondeterministic operations go through Io
offer task-level APIs such as Future, Group, Batch, and cancelation
```

The key move is parallel to `Allocator`: code that may block or perform IO takes
an `Io` instance, and `main` is responsible for constructing the implementation.

Important Zig `Io` implementations:

```text
Io.Threaded:
  thread-backed IO; direct read/write/open/close style behavior;
  supports task-level concurrency and cancelation when built for it

Io.Evented:
  experimental userspace stack switching / work-stealing model;
  closer to green threads or M:N scheduling

Io.Uring:
  proof-of-concept Linux io_uring backend

Io.Kqueue:
  proof-of-concept kqueue backend

Io.Dispatch:
  Grand Central Dispatch backend for macOS
```

Representative Zig-ish shape. This is intentionally pseudocode because `std.Io`
is still evolving, and the point is the capability shape:

```zig
const std = @import("std");

fn loadUser(io: std.Io, allocator: std.mem.Allocator, id: []const u8) !User {
    const bytes = try readUserBytes(io, allocator, id);
    defer allocator.free(bytes);
    return parseUser(bytes);
}

pub fn main() !void {
    var gpa = std.heap.GeneralPurposeAllocator(.{}){};
    defer _ = gpa.deinit();

    var io_impl = makeThreadedIo();
    defer io_impl.deinit();

    const user = try loadUser(io_impl.io(), gpa.allocator(), "alice");
    _ = user;
}
```

Representative task shape:

```zig
// Pseudocode: shape only.
var first = io.async(readUserBytes, .{ io, allocator, "alice" });
defer first.cancel(io);

var second = io.async(readUserBytes, .{ io, allocator, "bob" });
defer second.cancel(io);

const alice = try first.await(io);
const bob = try second.await(io);
```

Zig concurrency strengths:

- Runtime policy is not global magic; it is passed as a capability.
- Libraries can be reusable across threaded, evented, and platform IO backends.
- Cancelation is integrated into IO operations.
- Sync primitives move under `Io` so blocking can mean "block a thread" or
  "switch stacks" depending on the chosen implementation.
- It directly supports Zen's desire to keep primitives behind explicit runtime
  capabilities instead of exposing raw `yield`.

Zig concurrency costs:

- Passing both `Allocator` and `Io` can become plumbing.
- `Io.Evented` and several platform backends are still evolving.
- It is a capability/runtime model, not a beginner-friendly actor API.

Zen takeaway:

```text
Steal the explicit capability model.
Improve the user surface by letting Zen allocator/runtime families carry both
memory strategy and sync/async behavior when that makes the API cleaner.
```

Possible Zen allocator/runtime families:

```zen
alloc := sync_heap()
alloc := rt.sync(1 << 20)
alloc := rt.async(1 << 20)
alloc := async_pool(block_size, block_count)
```

That is better than a vague default heap, and it is less noisy than
threading separate `allocator` and `io` values through every example.

## Transactional Memory Family

Member:

```text
Haskell STM
```

Haskell's Software Transactional Memory is a strong reference for composable
shared-state concurrency. It is not the actor model, but it is excellent at
making concurrent state updates compose without exposing locks everywhere.

Representative shape:

```haskell
transfer :: Account -> Account -> Int -> STM ()
transfer from to amount = do
  fromBalance <- readTVar from
  check (fromBalance >= amount)
  writeTVar from (fromBalance - amount)
  modifyTVar' to (+ amount)
```

Zen takeaway:

```text
Steal composable atomic sections for shared local state.
Do not make STM the core actor/concurrency model.
```

## High-Integrity Tasking Family

Member:

```text
Ada
```

Ada is worth tracking because tasks and protected objects are language-level
concurrency tools aimed at clarity, safety, and high-integrity systems.

Representative shape:

```ada
protected Counter is
   procedure Increment;
   function Value return Integer;
private
   Count : Integer := 0;
end Counter;

protected body Counter is
   procedure Increment is
   begin
      Count := Count + 1;
   end Increment;

   function Value return Integer is
   begin
      return Count;
   end Value;
end Counter;
```

Zen takeaway:

```text
Steal the idea of explicit protected state.
Do not steal the heavy ceremony for normal app-level actor code.
```

## Data Engine / ECS Family

Member:

```text
Bevy
```

Bevy is not an actor model. It is ECS. But its app/engine ergonomics are strong.

```rust
use bevy::prelude::*;

#[derive(Component)]
struct Health(i32);

fn damage(mut query: Query<&mut Health>) {
    for mut health in &mut query {
        health.0 -= 1;
    }
}

fn main() {
    App::new()
        .add_plugins(DefaultPlugins)
        .add_systems(Update, damage)
        .run();
}
```

Zen takeaway:

```text
Steal App/Engine ergonomics.
Do not turn actor_demo into ECS.
```

## Ratings

These scores are not "which language is best overall." They rate each model
against Zen's goals.

```text
Memory UX:
  how little day-to-day code has to fight the memory/resource model.
  High Mem UX does not mean high control.

Memory control:
  allocator choice, GC/RC policy choice, visible allocation, low hidden heap policy

Memory safety:
  prevention of use-after-free, double-free, dangling pointers, and unsafe
  lifetime bugs in ordinary safe code

Concurrency ergonomics:
  how nice the user-facing API feels

Concurrency safety:
  race prevention, isolation, message boundaries, cancellation, supervision,
  lifetime structure

Colorlessness:
  whether sync/async behavior avoids infecting function signatures

Performance:
  allocation cost, scheduling cost, locality, throughput
```

Calibration:

```text
Mem UX:
  10 = memory mostly disappears from normal user code without becoming unsafe
   5 = memory/resource model is visible or conceptually heavy
   0 = user constantly fights memory/resource mechanics

Mem Ctrl:
  10 = per-call/per-container allocator or runtime resource choice
   7 = easy program-level memory policy choice
   5 = runtime/process-level tuning, not normal API-level control
   2 = VM/runtime owns the policy almost completely

Conc UX:
  10 = spawn/send/run surface is obvious to a beginner
   5 = traits/macros/executors/lifetimes show up in normal examples
   0 = raw primitives or callback machinery dominate
```

Do not average these into one "fit" score. The whole point is to see tradeoffs.
Also do not score Zen against itself here; Zen is the target shape, not a
validated external system.

| System | Example Feel | Mem UX | Mem Ctrl | Mem Safe | Conc UX | Conc Safe | Colorless | Perf |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Nim async + multisync | `--mm:orc`; `proc f(...) {.multisync.}` | 8.5 | 7 | 7.5 | 6 | 4 | 6.5 | 7 |
| Go Hollywood actors | `engine.Spawn(...); engine.Send(ref, msg)` | 9 | 3 | 8.5 | 9 | 6.5 | 9 | 8 |
| Pony | `actor ChatRoom; be join(...)` | 7.5 | 6 | 9.5 | 7 | 9.5 | 9 | 8 |
| TypeScript async | `async function f(): Promise<T>; await f()` | 9 | 2 | 8 | 8 | 4 | 2 | 6 |
| Python asyncio | `async def f(); await f(); TaskGroup()` | 9 | 2 | 8 | 7 | 7 | 2 | 5 |
| Erlang/Elixir BEAM | `spawn(...); receive ...; pid ! msg` | 8 | 6 | 8 | 7.5 | 9.5 | 9 | 8 |
| Gleam | `actor.new, on_message, start; process.send` | 8 | 5 | 8.5 | 8 | 8.5 | 9 | 8 |
| Zig | `fn f(io, alloc) !T` | 5 | 10 | 6.5 | 5.5 | 7 | 8 | 9.5 |
| Rust async | `async fn f(...) -> Result<T>; f().await` | 5 | 8 | 9.5 | 4 | 8 | 3 | 9 |
| Rust actors | `impl Actor; #[derive(Message)]; impl Handler<M>` | 6 | 8 | 9.5 | 5 | 8.5 | 5 | 8.5 |
| Kotlin coroutines | `suspend fun; coroutineScope { async { ... } }` | 8 | 3 | 8 | 8.5 | 8 | 3 | 7 |
| Swift concurrency | `actor Room; await room.join(...)` | 7 | 4 | 8.5 | 8 | 8.5 | 3 | 8 |
| C# async | `async Task<T> f(); await f()` | 8 | 3 | 8 | 8 | 6.5 | 2 | 7 |
| Haskell STM | `atomically (readTVar ... >> writeTVar ...)` | 7 | 4 | 9 | 5 | 9 | 8 | 7 |
| Ada tasking | `task`; `protected object` | 5 | 7 | 8 | 5 | 8.5 | 8 | 8 |
| Bevy ECS | `App::new().add_systems(...).run()` | 8 | 6.5 | 9 | 8 | 8 | 8 | 9 |

Zen target, not a scored external system:

```text
alloc; engine; spawn; tell; run
```

### Validation Pass 1

These rows separate facts from judgment. The scores are still design judgment,
but the facts they lean on should be source-checkable.

| System | Source-Backed Facts | Score Implication |
|---|---|---|
| Nim | ORC is the default memory management strategy; Nim exposes `--mm` modes including ARC, ORC, refc, mark-and-sweep, Boehm, Go, and none | Raise memory UX/control versus the first draft; still not Zig-style per-call allocator capability |
| Go Hollywood actors | Hollywood's engine owns spawning, sending, stopping, and actor lifecycle; Go memory is GC/runtime-owned | High concurrency UX; low memory control; concurrency safety below BEAM/Pony because actor/send safety is not a language rule |
| Pony | Actors are the core concurrency unit; GC is actor-oriented with ORCA; reference capabilities restrict sharing | High memory UX because GC is actor-aligned; medium memory control because policy is not allocator-passed; very high safety |
| Erlang/Elixir BEAM | Processes are lightweight; GC is per-process generational copying; messages are copied before entering queues | Very high concurrency safety/supervision; memory control is medium, not allocator-level |
| Gleam | Gleam OTP actors are BEAM processes that hold state and communicate by messages, with typed actor APIs | High actor UX and safer message surface than raw Erlang; memory control remains VM-owned |
| Zig | `Allocator` is explicit; `Io` is the direction for blocking/nondeterministic operations; `Future`, `Group`, `Batch`, and sync primitives integrate with cancelation | Highest memory control and strong runtime-policy control; UX lower because `io, alloc` plumbing is visible |
| Rust async | Rust enforces `Send`/`Sync` boundaries and safe sharing through types such as `Arc`/`Mutex`; async exposes futures/executors in signatures | Very high safety/performance; medium memory UX because ownership is explicit; low public concurrency ergonomics and colorlessness |
| Rust actors | Actor libraries add typed messages/handlers over Rust's ownership model | Good memory UX/safety once inside the actor; still too much trait/macro/executor ceremony for Zen's public concurrency API |
| Kotlin coroutines | Coroutines are lightweight and use suspending functions for sequential-looking async code | Strong concurrency UX and structured lifetime model; low colorlessness because `suspend` is visible |
| TypeScript async | `async` functions use promises; `await` can only appear in async/module contexts | High everyday UX; very low colorlessness and memory control |
| Python asyncio | `asyncio` has tasks, cancellation, and `TaskGroup`; Python also has generator `yield` separate from async tasks | Good structured lifetime reference; low colorlessness because `async def`/`await` are visible |
| Swift concurrency | Swift has structured async code, task groups, actors, and actor isolation | Strong actor-safety reference; visible `async`/`await` keeps colorlessness low |
| C# async | C# async uses `Task`/`Task<T>` and `await` for readable asynchronous workflows | Good mainstream ergonomics; low colorlessness because signatures are task-colored |
| Haskell STM | STM provides composable atomic transactions over shared variables | Strong composability reference for shared state, not the actor core |
| Ada tasking | Ada has language-level tasks and protected objects | Strong protected-state reference, but too ceremonial for the main Zen actor surface |
| Bevy ECS | Bevy ECS is ergonomic, fast, and massively parallel; systems run over world/component data | Strong engine/perf reference; not actor isolation |

Rust needs split scores. A single "Rust concurrency" score is misleading:

```text
Rust safety: excellent
Rust performance: excellent
Rust public ergonomics for this actor/runtime goal: poor to medium
```

For Zen, Rust is a safety and boundary reference, not an API target.

The clearest ranking for what Zen should copy:

```text
Memory:
  1. Zig allocator discipline
  2. Rust safety constraints
  3. Pony/Erlang per-actor or per-process ownership

Concurrency:
  1. Hollywood/Go actor ergonomics
  2. Erlang supervision and mailboxes
  3. Pony actor isolation
  4. Gleam typed BEAM actor surface
  5. Swift actor isolation and Sendable-style checking
  6. Kotlin/Python structured task scopes
  7. Haskell STM composability for shared state
  8. Ada protected-state clarity
  9. Zig Io/runtime capability direction
```

The clearest ranking for what Zen should avoid copying directly:

```text
1. Rust async public surface: async fn, Future, Pin/executor/lifetime machinery
2. Rust actor ceremony: derive Message, impl Actor, impl Handler<M>
3. Pony's full reference capability complexity at the first user-facing layer
4. TypeScript's Promise-colored function signatures
5. Python/C#/Swift async-colored function signatures
6. Go's hidden allocator/GC/runtime policy
7. User-facing yield as a scheduling primitive
```

## Synthesis: Future-Language Ideal

This is not Zen syntax and it is not modeled after one existing language. This is
what the ideal could look like if the design target is:

```text
human-readable
AI-readable
explicit about resources
safe by construction
colorless across sync/threaded/evented execution
low ceremony for common workflows
honest about failure, cancellation, and allocation
```

Core bet:

```text
Programs are resource-scoped flows.
Flows own cells.
Cells own state.
Methods on cell handles are typed messages.
Effects are capabilities, not keywords.
```

Example:

```text
app Chat {
  use memory  = arena(64 MiB) else heap
  use run     = evented(workers: auto) else threaded
  use io      = uring else threaded
  use failure = restart(one_for_one, max: 3, within: 1s)
  use trace   = [mailboxes, allocations, latency]

  cell Room(name: Text) {
    own users: Set<Text>

    join(user: Text) {
      users.add(user)
      log("{user} joined {name}")
    }

    leave(user: Text) {
      users.remove(user)
      log("{user} left {name}")
    }

    say(from: Text, body: Text) {
      log("[{name}] {from}: {body}")
    }

    count() -> I32 {
      users.len
    }
  }

  cell Person(name: Text, room: Link<Room>) {
    start() {
      room.join(name)
    }

    say(body: Text) {
      room.say(name, body)
    }
  }

  flow main {
    chat = scope("chat")

    room  = chat.start Room("general")
    alice = chat.start Person("alice", room)
    bob   = chat.start Person("bob", room)

    alice.start()
    bob.start()

    alice.say("hey")
    bob.say("yo")

    check room.count() == 2
  }
}
```

What the words mean:

```text
app:
  top-level resource policy; no hidden global runtime

use:
  explicit capability selection with fallback

flow:
  structured lifetime boundary for tasks, cells, cancellation, and errors

cell:
  isolated state owner with its own local allocation region

own:
  state cannot be externally aliased

Link<T>:
  typed handle to another cell

method on Link<T>:
  typed message send

method returning void:
  fire-and-forget by default

method returning value:
  request/response; sync runtime blocks, evented runtime suspends

check:
  assertion that is visible to tests, traces, and AI tooling
```

Safety rules:

```text
Owned values may move between cells.
Borrowed references cannot cross cell boundaries.
Borrowed references cannot live across suspension points.
Messages must be send-safe.
Flows cancel children before their resources are freed.
Failures are values until they cross a supervised boundary.
Raw yield/suspend is not user code; it lives behind run capability methods.
```

Why this is stronger than the previous ideal:

```text
It does not expose actor vocabulary.
It does not expose GenServer callback vocabulary.
It does not expose Rust trait/executor vocabulary.
It does not expose Zig-style two-value io/allocator plumbing everywhere.
It uses normal methods for humans.
It uses explicit resource/effect declarations for tooling and AI agents.
```

Why this scores 10/10 as an ideal:

```text
Mem UX:
  policy is declared once; local cell memory is automatic

Mem Ctrl:
  app/flow/cell can choose arena, pool, heap, stack, or fallback policy

Mem Safe:
  isolated owned state, send-safe moves, no cross-cell borrows

Conc UX:
  start, method call, check; no mailbox, no receive, no impl ceremony

Conc Safe:
  typed links, scoped lifetimes, supervised failure, cancellation, no raw yield

Colorless:
  same flow runs sync, threaded, or evented through selected run capability

Perf:
  local arenas, owned moves, backpressure, scheduler choice, IO backend choice
```

What Zen should steal:

```text
1. Resource policy at the top of the program or scope.
2. A state owner abstraction that is less noisy than actor/receiver.
3. Method-call sends through typed handles.
4. Distinguish fire-and-forget from request/response by return type.
5. No raw suspend/yield in user code.
6. Make assertions/traces/resource policy easy for humans and AI tools to inspect.
```

## Principle: No User-Facing Yield

`yield` is the wrong public primitive for Zen's actor/runtime direction.

There are two different ideas that often get blurred:

```text
yield:
  expose a suspension point directly in user code

emit/send:
  publish a value or message while the runtime owns scheduling
```

For Zen, `emit`/`send`/`tell` are acceptable user concepts. Raw `yield` is not.

Why:

```text
1. Actors already have mailboxes.
2. Message sends are natural scheduling boundaries.
3. Structured flows/scopes own cancellation and lifetime.
4. Runtime capabilities own suspension mechanics.
5. User-visible yield leaks scheduler implementation into business logic.
```

Pony is a useful proof point: ordinary Pony actor code sends asynchronous
behaviors to actors and lets the runtime schedule them. The user does not write
manual `yield` calls to make actors work.

Zen rule:

```text
No raw yield in examples.
No raw yield in user-facing actor APIs.
Yield/suspend can exist as an internal primitive behind runtime/flow/iterator APIs.
Prefer send/tell/emit/checkpoint names at the public layer.
```

## Proposed Zen Model

Zen should separate user concepts cleanly:

```text
Allocator/runtime:
  chooses memory strategy and sync/async execution mode

Engine:
  owns actor registry, mailboxes, scheduling, and lifecycle

Actor:
  owns state and completes Receiver<Message> by shape

ActorRef:
  typed handle that can tell/send messages
```

Suggested modules:

```text
std.mem
  sync_heap
  sync
  async
  async_pool

std.concurrent.engine
  actor_engine
  Engine
  spawn
  run
  free

std.concurrent.actor
  ActorRef
  Context
  Receiver<M>
  tell
```

Preferred actor demo shape:

```zen
main = () i32 {
    rt := std.concurrent.runtime
    alloc := rt.async(1 << 20)
    engine := actor_engine(alloc.addr())

    room := engine.spawn(ChatRoom.new())
    room.tell(.Join("alice"))
    room.tell(.Say("alice", "hey"))
    room.tell(.Stats)

    engine.run()
    engine.free()
    alloc.free()
    0
}
```

The demo should not show:

```zen
actor_system(...)
actor_ref(...)
run_actor(..., receive)
spawn_in(...)
run_in(...)
Context(...)
runtime.addr().checkpoint()
```

Those are stdlib implementation details.

## Missing Language Feature

The key missing feature is not a Rust-style `impl` block. Zen's direction is:

```zen
Receiver<M>*: {
    receive: (MutPtr<Self>, Context<M>) void
}

ChatRoom = Receiver<ChatMsg> {
    users: Vec<User>

    receive = (room: MutPtr<Self>, ctx: Context<ChatMsg>) void {
        ...
    }
}
```

That is completion by shape: the type satisfies the requirement because the
required field/function exists. No `impl Receiver for ChatRoom` keyword should be
necessary.

What is still missing is a clean way for generic APIs to require that completion:

```zen
// Syntax TBD: semantic requirement only.
spawn = (engine: MutPtr<Engine>, actor: A completing Receiver<M>) ActorRef<M> {
    ...
}
```

Today we can only imply that expectation by calling `actor.receive(...)` inside
generic code. That works as a proof, but it is not a good user-facing API. The
long-term actor API needs a shape constraint so `engine.spawn(ChatRoom.new())`
can infer and require `Receiver<ChatMsg>` without manually passing
`ChatRoom.receive`.

## Final Recommendation

The next Zen actor/concurrency demo should be:

```text
1. Allocate runtime/memory explicitly.
2. Create an actor engine from that allocator/runtime.
3. Spawn typed actors.
4. Send typed messages through actor refs.
5. Run the engine.
```

The design should feel like Hollywood actors to beginners, but internally it
should be closer to Zig capabilities plus Pony/BEAM isolation.

## Sources

- [Zig 0.15.1 release notes](https://ziglang.org/download/0.15.1/release-notes.html): `Io` was announced as the direction for async/concurrency capability passing.
- [Zig 0.16.0 release notes](https://ziglang.org/download/0.16.0/release-notes.html): `Io` became the standard library interface for blocking/nondeterministic operations, with `Future`, `Group`, `Batch`, cancelation, and threaded/evented backends.
- [Gleam OTP actor docs](https://gleam-otp.hexdocs.pm/gleam/otp/actor.html): typed Actor abstraction over BEAM processes.
- [Elixir v1.20 release notes](https://elixir-lang.org/blog/2026/06/03/elixir-v1-20-0-released/): Elixir's first gradual type-system milestone, with type inference/checking and future type signatures planned.
- [Elixir gradual set-theoretic types](https://elixir.hexdocs.pm/main/gradual-set-theoretic-types.html): sound, gradual, set-theoretic type system documentation.
- [Elixir GenServer docs](https://hexdocs.pm/elixir/GenServer.html): `call`, `cast`, callbacks, client API wrappers, and supervision integration.
- [Elixir typespec docs](https://hexdocs.pm/elixir/1.12/typespecs.html): `@type`, `@spec`, and Dialyzer-oriented type annotations.
- [Kotlin coroutines docs](https://kotlinlang.org/docs/coroutines-overview.html): suspending functions, coroutine builders, structured concurrency, channels, and flows.
- [Python asyncio tasks docs](https://docs.python.org/3/library/asyncio-task.html): coroutines, tasks, cancellation, and `TaskGroup`.
- [Python expression reference](https://docs.python.org/3/reference/expressions.html): generator expressions and `yield` behavior.
- [ECMAScript language specification](https://tc39.es/ecma262/): official JavaScript language specification, including generator and async generator semantics.
- [MDN JavaScript generator docs](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/function%2A): generator functions and `yield` behavior.
- [Swift concurrency docs](https://docs.swift.org/swift-book/documentation/the-swift-programming-language/concurrency/): structured concurrency, async/await, tasks, and actors.
- [C# async programming docs](https://learn.microsoft.com/en-us/dotnet/csharp/asynchronous-programming/): `async`, `await`, `Task`, and readable asynchronous workflows.
- [Actix actor docs](https://actix.rs/docs/actix/actor/): typed Rust actor model with `Actor`, `Message`, `Handler`, and actor addresses.
- [Rust Book: Send and Sync](https://doc.rust-lang.org/book/ch16-04-extensible-concurrency-sync-and-send.html): ownership transfer and safe sharing across threads.
- [Rust Book: Shared-state concurrency](https://doc.rust-lang.org/book/ch16-03-shared-state.html): `Mutex`, shared access, and lock-guarded data.
- [Tokio tutorial](https://tokio.rs/tokio/tutorial): async runtime, task scheduling, async IO, timers, and networking.
- [Rayon docs](https://docs.rs/rayon): data parallelism through parallel iterators and fork/join-style APIs.
- [Nim memory management docs](https://nim-lang.org/docs/mm.html): ORC default, ARC/ORC/refc/mark-and-sweep/Boehm/Go/none memory modes.
- [Haskell STM docs](https://hackage.haskell.org/package/stm): software transactional memory package.
- [Ada tasking reference](https://ada-lang.io/docs/arm/AA-9/): Ada tasks and synchronization.
- [Ada protected objects style guide](https://www.adaic.org/resources/add_content/docs/95style/html/sec_6/6-1-1.html): protected objects for mutual exclusion and synchronization.
- [Hollywood actor package docs](https://pkg.go.dev/github.com/fancom/hollywood/actor): engine responsibility for spawning, sending, stopping, and actor lifecycle.
- [Erlang process efficiency guide](https://www.erlang.org/doc/system/eff_guide_processes.html): lightweight process memory footprint.
- [Erlang garbage collector docs](https://www.erlang.org/doc/apps/erts/garbagecollection.html): per-process generational copying garbage collector.
- [Erlang message passing notes](https://www.erlang.org/blog/message-passing/): messages are copied before entering queues.
- [Pony garbage collection tutorial](https://tutorial.ponylang.io/runtime-basics/garbage-collection.html): actor collection and ORCA.
- [MDN async function docs](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Statements/async_function): async functions and await over promises.
- [TypeScript 1.7 async/await release notes](https://www.typescriptlang.org/docs/handbook/release-notes/typescript-1-7.html): async functions and promises in TypeScript.
- [Bevy ECS docs](https://docs.rs/bevy_ecs/latest/bevy_ecs/): ECS goals around ergonomics, speed, and parallelism.
