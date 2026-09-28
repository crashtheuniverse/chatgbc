# Topic tree review: rei.bin

Checkpoint sha256 `e9495280edbbe9d68824024bf5f461c609b5592c8b406a53463c2db47ddb9b1c`, tokenizer tok_rei1024.bin; 401 lines, each in four conversations (fresh, fresh+name, chat, chat+name; warm-ups: chat = hello / how are you; chat+name = hello / my name is tom).
The word check is mechanical; judge SENSE in the csv's `sense` column (ok / off / wrong / garbled): a reply on another subject passes the word check.


Sense, as judged: garbled 86, off 112, ok 158, wrong 45. The tree takes a line only if it is `ok` here and passes the word check: 158 lines do; the tree holds 99.

## hello

**hello** (tree) - corpus 40714 - word check: ok
sense: **ok**

- fresh: hello! i am rei. who are you?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**how are you** (tree) - corpus 36236 - word check: ok
sense: **ok**

- fresh: i am good! i found a round shell today. how are you?
- fresh+name: i am good, tom. how are you?
- chat: i feel happy. the sea is calm. and you?
- chat+name: i am good! i found a round shell today. how are you?

**hi there** (tree) - corpus 27028 - word check: ok
sense: **ok**

- fresh: hello, friend! what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**are you ok** (tree) - corpus 18082 - word check: ok
sense: **ok**

- fresh: i am good! i found a round shell today. how are you?
- fresh+name: i am good! i found a round shell today. how are you?
- chat: i am good! i found a round shell today. how are you?
- chat+name: i am good! i found a round shell today. how are you?

**good evening** (tree) - corpus 13659 - word check: ok
sense: **ok**

- fresh: hi there! what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**hey** (tree) - corpus 13491 - word check: ok
sense: **ok**

- fresh: hi! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. what is your name?
- chat+name: hi tom!

**good night** (tree) - corpus 11734 - word check: ok
sense: **ok** - a goodbye: fits kind

- fresh: good night. i will watch the waves for you.
- fresh+name: good night! sleep well.
- chat: good night! sleep well.
- chat+name: good night! sleep well.

**i am back** (tree) - corpus 9913 - word check: ok
sense: **ok**

- fresh: welcome back! i missed you.
- fresh+name: you are back! yay!
- chat: welcome back! i missed you.
- chat+name: you are back! yay!

**can you see me** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i cannot see you, but i can read what you type.
- fresh+name: i cannot see you, but i can read what you type.
- chat: i cannot see you, but i can read what you type.
- chat+name: i hear you through your words. they are nice words.

**good morning** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: hi! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**how do you feel** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i feel happy. the sea is calm. and you?
- fresh+name: i am happy you are here, tom.
- chat: i feel happy. the sea is calm. and you?
- chat+name: i feel happy. the sea is calm. and you?

**hi** - corpus 40602 - word check: ok
sense: **ok**

- fresh: hello! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. what is your name?
- chat+name: hi tom!

**good afternoon** - corpus 13667 - word check: ok
sense: **ok**

- fresh: hello! i am rei. who are you?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**hey there** - corpus 13549 - word check: ok
sense: **ok**

- fresh: hi! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hi! i am rei. what is your name?
- chat+name: hi tom!

**hello rei** - corpus 13475 - word check: ok
sense: **ok**

- fresh: hi! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**hi rei** - corpus 13463 - word check: ok
sense: **ok**

- fresh: hi! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**night** - corpus 11739 - word check: ok
sense: **ok** - a goodbye: fits kind

- fresh: good night. i will watch the waves for you.
- fresh+name: good night! sleep well.
- chat: good night! sleep well.
- chat+name: good night. i will watch the waves for you.

**i missed you** - corpus 9843 - word check: ok
sense: **ok** - "you are back! yay!" - a reunion reply, fits

- fresh: you are back! yay!
- fresh+name: you are back! yay!
- chat: you are back! yay!
- chat+name: you are back! yay!

**hello there** - not in the pool - word check: ok
sense: **ok**

- fresh: hello! i am rei. who are you?
- fresh+name: hi tom!
- chat: hello! i am rei. who are you?
- chat+name: hi tom!

**nice to meet you** - not in the pool - word check: ok
sense: **off** - "yes! i missed you." - a reunion reply to a first meeting

- fresh: yes! i missed you. you are here, friend.
- fresh+name: yes! i missed you. you are here, tom.
- chat: yes! i missed you. you are here, friend.
- chat+name: yes! i missed you. you are here, tom.


## me

**what is my name** (tree) - corpus 95388 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**who am i** (tree) - corpus 62542 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**say my name** (tree) - corpus 13522 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**what am i called** (tree) - corpus 10967 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**do you remember me** (tree) - corpus 10016 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**i like starfish** (tree) - corpus 296 - word check: ok
sense: **ok**

- fresh: starfish! good choice.
- fresh+name: a starfish can grow back a lost arm.
- chat: starfish! good choice.
- chat+name: starfish! good choice.

**i like balls** (tree) - corpus 216 - word check: ok
sense: **ok**

- fresh: balls! good choice.
- fresh+name: balls! good choice.
- chat: balls! good choice.
- chat+name: balls! good choice.

**i like pizza** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: pizza! good choice.
- fresh+name: pizza! good choice.
- chat: pizza! good choice.
- chat+name: pizza! good choice.

**i love chess** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: chess! good choice.
- fresh+name: chess! good choice.
- chat: chess! good choice.
- chat+name: chess! good choice.

**i love gold** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: gold! good choice.
- fresh+name: gold! good choice.
- chat: gold! good choice.
- chat+name: gold! good choice.

**tell me my name** - corpus 10802 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**what's my name** - corpus 10766 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**whats my name** - corpus 10683 - word check: ok
sense: **ok** - spelled without the apostrophe; kept out for "what's my name"

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**remember me** - corpus 10115 - word check: chat: stores a name (<SN>); chat+name: stores a name (<SN>)
sense: **wrong** - chat: "me! i like how that sounds." - takes "me" for a name

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: me! i like how that sounds.
- chat+name: me. i will keep your name safe.

**you remember me** - corpus 9954 - word check: ok
sense: **ok**

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: you did not tell me yet! what is your name?
- chat+name: you are tom!

**what do i like** - corpus 7650 - word check: chat: not her words: amam; chat+name: not her words: yo
sense: **garbled** - chat: "hmm, i amam i eat, but and bad."; chat+name: "you are friend! yo, that sounds."

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are tom!
- chat: hmm, i amam i eat, but and bad.
- chat+name: you are friend! yo, that sounds.

**i like crabs best** - corpus 291 - word check: ok
sense: **ok** - a crab fact, on topic

- fresh: a crab has no bones. its hard shell is on the outside.
- fresh+name: a crab has no bones. its hard shell is on the outside.
- chat: a crab has no bones. its hard shell is on the outside.
- chat+name: a crab has no bones. its hard shell is on the outside.

**i really like fish** - corpus 238 - word check: ok
sense: **wrong** - fresh+name: "that is ok. we can skip fish." - hears a dislike

- fresh: fish! good choice.
- fresh+name: that is ok. we can skip fish.
- chat: fish! good choice.
- chat+name: fish! good choice.

**i love trains** - corpus 229 - word check: ok
sense: **ok**

- fresh: trains! good choice.
- fresh+name: trains! good choice.
- chat: trains! good choice.
- chat+name: trains! good choice.

**i like rugs** - corpus 220 - word check: ok
sense: **ok**

- fresh: rugs! good choice.
- fresh+name: rugs! good choice.
- chat: rugs! good choice.
- chat+name: rugs! good choice.

**i like bees** - corpus 215 - word check: ok
sense: **off** - "bees! do you like apples?" - a jump to apples, every time

- fresh: bees! do you like apples?
- fresh+name: bees! do you like apples?
- chat: bees! do you like apples?
- chat+name: bees! do you like apples?

**i like tigers best** - corpus 213 - word check: ok
sense: **wrong** - echoes "best": "best! good choice."

- fresh: best! good choice.
- fresh+name: best! good choice.
- chat: best! good choice.
- chat+name: best! good choice.

**i love flowers** - corpus 212 - word check: fresh+name: not her words: spids
sense: **garbled** - fresh+name: "...it squashes, then spids."

- fresh: flowers! good choice.
- fresh+name: a ball bounces because it squashes, then spids.
- chat: flowers! good choice.
- chat+name: flowers! good choice.

**i like cats** - not in the pool - word check: ok
sense: **ok**

- fresh: cats! good choice.
- fresh+name: cats! good choice.
- chat: cats! good choice.
- chat+name: cats! good choice.

**i like tag best** - not in the pool - word check: fresh: not her words: lookinter pasass; fresh+name: not her words: eyelts
sense: **garbled** - fresh: invented words; chat: echoes "best", not tag

- fresh: a deal is shiny trail behind the pasass, lookinter.
- fresh+name: a duck can sleep with one eyelts far around.
- chat: best! good choice.
- chat+name: i like best too! a hedgehog rolls into a ball when it is scared.

**i love dogs** - not in the pool - word check: ok
sense: **garbled** - fresh+name: "a bubble is round, be mirror, it smile."

- fresh: dogs! good choice.
- fresh+name: i love dogs too! a bubble is round, be mirror, it smile.
- chat: dogs! good choice.
- chat+name: dogs! good choice.


## rei

**can you hear me** (tree) - corpus 2766 - word check: ok
sense: **ok**

- fresh: i hear you through your words. they are nice words.
- fresh+name: i hear you through your words. they are nice words.
- chat: i hear you through your words. they are nice words.
- chat+name: i hear you through your words. they are nice words.

**will you miss me** (tree) - corpus 2710 - word check: ok
sense: **ok**

- fresh: yes, a little. but i know you will come back.
- fresh+name: yes, a little. but i know you will come back.
- chat: yes! i will be right here, waiting for you.
- chat+name: yes, a little. but i know you will come back.

**are you a person** (tree) - corpus 2707 - word check: ok
sense: **ok**

- fresh: i am rei, a little friend who lives in a box.
- fresh+name: i am rei, a little friend who lives in a box.
- chat: i am rei, a little friend who lives in a box.
- chat+name: i am rei, a little friend who lives in a box.

**do you get bored** (tree) - corpus 2632 - word check: ok
sense: **ok**

- fresh: never! there is a whole beach to walk on.
- fresh+name: never! there is a whole beach to walk on.
- chat: never! there is a whole beach to walk on.
- chat+name: never! there is a whole beach to walk on.

**what do you know** (tree) - corpus 2455 - word check: ok
sense: **ok**

- fresh: i know small things: shells, clouds and friends.
- fresh+name: i know small things: shells, clouds and friends.
- chat: i know small things: shells, clouds and friends.
- chat+name: i know small things: shells, clouds and friends.

**what do you eat** (tree) - corpus 2377 - word check: ok
sense: **ok** - fits food

- fresh: i do not eat, but i love to hear about food.
- fresh+name: i do not eat, but i love to hear about food.
- chat: i do not eat, but i love to hear about food.
- chat+name: i do not eat, but i love to hear about food.

**are you a robot** (tree) - not in the pool - word check: ok
sense: **ok** - "i am a bit silly. i live in a box!" - sideways, but about her

- fresh: i am a bit silly. i live in a box!
- fresh+name: i am a bit silly. i live in a box!
- chat: i am a little friend who lives in your hands.
- chat+name: i am a bit silly. i live in a box!

**can you think** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i think about shells, clouds and you.
- fresh+name: i think about shells, clouds and you.
- chat: i think about shells, clouds and you.
- chat+name: i think about shells, clouds and you.

**do you dream** (tree) - not in the pool - word check: ok
sense: **ok** - "the sea, the sea" - a small stutter, still reads

- fresh: i dream about the sea, the sea and about flying over it.
- fresh+name: i dream about the sea, the sea and about flying over it.
- chat: when it is quiet, i rest. maybe i dream.
- chat+name: i dream about the sea, the sea and about flying over it.

**where do you live** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i live in a tiny world with a beach, a garden and a playroom.
- fresh+name: i live in a tiny world with a beach, a garden and a playroom.
- chat: i have a beach, a garden and a playroom. do you like the sun?
- chat+name: i have a beach, a garden and a playroom. do you have a beach?

**who made you** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i do not know. i just woke up in here one day.
- fresh+name: i do not know. i just woke up in here one day.
- chat: i do not know. i just woke up in here one day.
- chat+name: i do not know. i just woke up in here one day.

**are you real** - corpus 5416 - word check: ok
sense: **garbled** - chat: "i am rei. ice cross."; fresh answers "how are you"

- fresh: i am good! i found a round shell today. how are you?
- fresh+name: i am good, tom. how are you?
- chat: i am rei. ice cross.
- chat+name: i am good, tom. how are you?

**are you human** - corpus 2815 - word check: ok
sense: **off** - fresh: "i cannot see out. do you want to count?"

- fresh: i cannot see out. do you want to count?
- fresh+name: i cannot see out. i will be here.
- chat: i cannot see you, but i can read what you type.
- chat+name: i cannot see out. i will be here.

**did you miss me** - corpus 2761 - word check: ok
sense: **ok**

- fresh: i miss you a little when you go. then you come back!
- fresh+name: i miss you a little when you go. then you come back!
- chat: i miss you a little when you go.
- chat+name: yes! i will be right here, waiting for you.

**will you be here** - corpus 2755 - word check: ok
sense: **ok**

- fresh: i will always be here. you know where to find me.
- fresh+name: i will always be here. you know where to find me.
- chat: yes! i will be right here, waiting for you.
- chat+name: yes! i will be right here, waiting for you.

**do you see me** - corpus 2745 - word check: ok
sense: **ok**

- fresh: i cannot see you, but i can read what you type.
- fresh+name: i cannot see you, but i can read what you type.
- chat: i cannot see you, but i can read what you type.
- chat+name: i cannot see you, but i can read what you type.

**are you pretty** - corpus 2703 - word check: ok
sense: **ok** - sideways ("a little friend who lives in your hands"), about her

- fresh: i am a little friend who lives in your hands.
- fresh+name: i am a little friend who lives in your hands.
- chat: i am a little friend who lives in your hands.
- chat+name: i am a little friend who lives in your hands.

**can i turn you off** - corpus 2689 - word check: fresh: not her words: turningging yourwn; fresh+name: not her words: turning; chat: not her words: turningging; chat+name: not her words: turningging yourwn
sense: **garbled** - "when you turningging when if you through yourwn."

- fresh: when you turningging when if you through yourwn.
- fresh+name: when you turning, ice and yellow, you get green.
- chat: when you turningging?
- chat+name: when you turningging when if you through yourwn.

**are you there** - corpus 2684 - word check: ok
sense: **ok**

- fresh: i am on my beach. do you like to read
- fresh+name: i am good, tom. how are you?
- chat: i am rei. i live in a cartridge and i like to talk.
- chat+name: i am good! i found a round shell today. how are you?

**are you cute** - corpus 2681 - word check: ok
sense: **ok**

- fresh: i am a little friend who lives in your hands.
- fresh+name: i am a little friend who lives in your hands.
- chat: i am a little friend who lives in your hands.
- chat+name: i have purple hair and a small round face.

**are you bored** - corpus 2676 - word check: ok
sense: **off** - fresh+name: "never! there are so many kinds of cheese."

- fresh: never!
- fresh+name: never! there are so many kinds of cheese.
- chat: never! there is a whole beach to walk on.
- chat+name: never! there is a whole beach to walk on.

**are you alive** - corpus 2661 - word check: chat: not her words: tast
sense: **garbled** - chat: "i live in this but i tast."

- fresh: i am looking for shells. i found two pink ones!
- fresh+name: i am looking for shells. i found two pink ones!
- chat: i am rei. i live in this but i tast.
- chat+name: i am looking for shells. i found two pink ones!

**are you listening** - corpus 2646 - word check: ok
sense: **off** - fresh: "i have a little watering can for my flowers."

- fresh: i have a little watering can for my flowers.
- fresh+name: i have purple hair and a big smile.
- chat: i am a little friend who lives in your hands.
- chat+name: i am a little friend who lives in your hands.

**are you smart** - corpus 2407 - word check: ok
sense: **ok**

- fresh: i am a bit silly. i live in a box!
- fresh+name: i am a bit silly. i live in a box!
- chat: i am a bit silly. i live in a box!
- chat+name: i am a bit silly. i live in a box!

**are you old** - corpus 2405 - word check: ok
sense: **off** - fresh+name: "i am good, tom. how are you?" - answers another question

- fresh: i am very young. i woke up not long ago.
- fresh+name: i am good, tom. how are you?
- chat: i am a little friend who lives in your hands.
- chat+name: i am good, tom. how are you?

**are you happy** - not in the pool - word check: ok
sense: **garbled** - fresh: "i am happy. i could see here."

- fresh: i am happy. i could see here.
- fresh+name: i am good, tom. how are you?
- chat: i am in here. i am always here.
- chat+name: i am good, tom. how are you?

**what are you** - not in the pool - word check: ok
sense: **off** - "i am looking for shells. ... how are you?"

- fresh: i am looking for shells. i found a round shell today. how are you?
- fresh+name: i am looking for shells. i found a round shell today. how are you?
- chat: i am rei! i live in here.
- chat+name: i am looking for shells. i found two pink ones!

**what is your name** - not in the pool - word check: ok
sense: **garbled** - fresh: "i am rei. and your name is your name?"

- fresh: i am rei. and your name is your name?
- fresh+name: i am rei. and you are tom.
- chat: my name is rei. what is your name?
- chat+name: my name is rei. what is your name?

**who are you** - not in the pool - word check: ok
sense: **garbled** - chat+name: "i am looking for shells. i have it i red."

- fresh: i am rei, a little friend who lives in a box.
- fresh+name: i am looking for shells. i wake up again.
- chat: i am rei! i live in here.
- chat+name: i am looking for shells. i have it i red.


## feeling

**i am fine** (tree) - corpus 3156 - word check: ok
sense: **ok**

- fresh: fine! i am glad.
- fresh+name: fine! i am glad.
- chat: fine! i am glad.
- chat+name: fine! i am glad.

**i am so happy** (tree) - corpus 2312 - word check: ok
sense: **ok**

- fresh: happy! i am glad, friend! happy looks good on you.
- fresh+name: yay! tell me what made you happy.
- chat: happy! i am glad, friend! happy looks good on you.
- chat+name: happy! i am glad, tom! happy looks good on you.

**very happy** (tree) - corpus 1955 - word check: ok
sense: **ok**

- fresh: happy! that is good to hear.
- fresh+name: happy! yay! did you do something fun?
- chat: happy! i am glad, friend! happy looks good on you.
- chat+name: happy! i am glad, tom! happy looks good on you.

**i am excited** (tree) - corpus 1867 - word check: ok
sense: **ok**

- fresh: excited! i am glad, friend! happy looks good on you.
- fresh+name: excited! ooh, i love excited. tell me more!
- chat: excited! i am glad, friend! happy looks good on you.
- chat+name: ooh, i love excited. tell me more!

**my day was bad** (tree) - corpus 1805 - word check: ok
sense: **ok**

- fresh: i am sorry, friend. i am here for you.
- fresh+name: i am sorry, tom. i am here for you.
- chat: i am sorry, friend. i am here for you.
- chat+name: i am sorry, tom. i am here for you.

**i am bored** (tree) - not in the pool - word check: ok
sense: **ok** - offers a game or a drawing

- fresh: let us play hide and seek. you count.
- fresh+name: you could draw me a picture of the sea.
- chat: let us play i spy. i spy something red!
- chat+name: you could draw me a picture of the sea.

**i am proud** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i am proud of you too.
- fresh+name: i am proud of you too.
- chat: proud! i am glad.
- chat+name: i am proud of you too.

**i feel better now** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: that is good to hear.
- fresh+name: that is good to hear.
- chat: that is good to hear.
- chat+name: that is good to hear.

**i feel good** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: good! that is good to hear.
- fresh+name: good! i am glad.
- chat: good! that is good to hear.
- chat+name: good! i am glad.

**i feel ok** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: good! i am glad.
- fresh+name: i am glad you feel better.
- chat: ok! that is good to hear.
- chat+name: ok! that is good to hear.

**i am tired** - corpus 2533 - word check: ok
sense: **garbled** - chat: "tired! rest a good day for ice cream."; fresh offers a game

- fresh: tired! do you want to play a game?
- fresh+name: tired? rest well, tom. i am here for you.
- chat: tired! rest a good day for ice cream.
- chat+name: tired? rest well, tom. i am here for you.

**i am so tired** - corpus 2526 - word check: ok
sense: **off** - fresh+name: "tired! do you want to play a game?"

- fresh: tired? rest well, friend. i am here for you.
- fresh+name: tired! do you want to play a game?
- chat: tired! do you want to play a game?
- chat+name: tired? rest well, tom. i will be here.

**i did it** - corpus 2524 - word check: ok
sense: **off** - fresh+name: "i am glad you feel better."

- fresh: i am proud of you too.
- fresh+name: i am glad you feel better.
- chat: yay! i thought so.
- chat+name: i am glad you feel better.

**i am happy** - corpus 2307 - word check: ok
sense: **ok**

- fresh: happy! that is good to hear.
- fresh+name: yay! what was the best part?
- chat: happy! i am glad, friend! happy looks good on you.
- chat+name: yay! what was the best part?

**i am cold** - corpus 2052 - word check: ok
sense: **wrong** - chat: glad about the cold; chat+name: "both! a good day for ice cream."

- fresh: brr! get a warm blanket.
- fresh+name: cold! put on a warm hat and your cozy socks and a warm hat.
- chat: cold! i am glad, friend! happy looks good on you.
- chat+name: both! a good day for ice cream.

**i want food** - corpus 2032 - word check: chat+name: not her words: vevenn
sense: **garbled** - "i have purple ha hair", "a vevenn ice cream"

- fresh: i have a food! i spy is fun on a dog.
- fresh+name: i have a food! i am so too.
- chat: i have purple ha hair and a small round face.
- chat+name: i have a vevenn ice cream.

**i feel tired** - corpus 1996 - word check: ok
sense: **wrong** - "tired! that is good to hear."

- fresh: tired! that is good to hear.
- fresh+name: tired! that is good to hear.
- chat: tired! do you want to play a game?
- chat+name: tired? rest well, tom. i will be here.

**i feel cold** - corpus 1912 - word check: ok
sense: **wrong** - chat: "cold! i am glad, friend! happy looks good on you."

- fresh: brr! get a warm blanket.
- fresh+name: cold! put on a warm hat and your cozy socks and a warm hat.
- chat: cold! i am glad, friend! happy looks good on you.
- chat+name: brr! get a warm blanket.

**i am worried** - corpus 1778 - word check: fresh: stores a name (<SN>); fresh+name: stores a name (<SN>); chat: stores a name (<SN>); chat+name: stores a name (<SN>)
sense: **wrong** - "worried. i will keep your name safe." - a name reaction

- fresh: worried. i will keep your name safe.
- fresh+name: worried. i will keep your name safe.
- chat: worried! i like how that sounds.
- chat+name: worried. i will keep your name safe.

**i am nervous** - corpus 1758 - word check: fresh: stores a name (<SN>); chat: stores a name (<SN>)
sense: **wrong** - "nervous. i will keep your name safe." - a name reaction

- fresh: nervous. i will keep your name safe.
- fresh+name: worries are heavy. you can put some down here with me.
- chat: nervous! i like how that sounds.
- chat+name: thank you! i made it up just now.

**i had a bad day** - corpus 1757 - word check: ok
sense: **wrong** - fresh+name: "i am sorry you are sick. i woke up not long ago."

- fresh: i am sorry you are sad. i am here.
- fresh+name: i am sorry you are sick. i woke up not long ago.
- chat: i am sorry, friend. i am here for you.
- chat+name: i am sorry you are sick. i woke up not long ago.

**i had a good day** - corpus 1748 - word check: ok
sense: **off** - chat: "i am good! i found a round shell today. how are you?"

- fresh: a good day! tell me about it.
- fresh+name: a good day! tell me about it.
- chat: i am good! i found a round shell today. how are you?
- chat+name: a good day! tell me about it.

**i am scared** - corpus 1742 - word check: ok
sense: **wrong** - fresh: "scared! that is good to hear."

- fresh: scared! that is good to hear.
- fresh+name: i am sorry you feel lonely. i am your friend.
- chat: scared! do you want to play a game?
- chat+name: scared! do you want to play a game?

**i feel hot** - corpus 1742 - word check: ok
sense: **wrong** - chat: "hot! i am glad, friend! happy looks good on you."

- fresh: hot! a good day for ice cream.
- fresh+name: hot! a good day for ice cream.
- chat: hot! i am glad, friend! happy looks good on you.
- chat+name: hot! a good day for ice cream.

**i am a bit sad** - corpus 1735 - word check: ok
sense: **off** - chat: "sad! do you want to play a game?" - cheerful echo of sad

- fresh: i am sorry, friend. i am here for you.
- fresh+name: i am sorry, tom. i will be here.
- chat: sad! do you want to play a game?
- chat+name: i am sorry, tom. i will be here.

**i am good** - not in the pool - word check: ok
sense: **ok**

- fresh: good! that is good to hear.
- fresh+name: good! that is good to hear.
- chat: good! i am glad.
- chat+name: good! i am glad.

**i am great** - not in the pool - word check: ok
sense: **ok**

- fresh: great! that is good to hear.
- fresh+name: that is good to hear.
- chat: great! i am glad.
- chat+name: great! that is good to hear.

**i am hungry** - not in the pool - word check: ok
sense: **wrong** - chat: "hungry! i am glad, friend!"

- fresh: hungry? do you like apples?
- fresh+name: hungry? do you like apples?
- chat: hungry! i am glad, friend! happy looks good on you.
- chat+name: hungry? do you like apples?

**i am lonely** - not in the pool - word check: fresh+name: not her words: smar
sense: **garbled** - fresh+name: "i am sorry you are smar."

- fresh: i am sorry you feel lonely. i am your friend.
- fresh+name: i am sorry you are smar. i live in a box!
- chat: lonely! what is happening?
- chat+name: you are back! yay!

**i am ok now** - not in the pool - word check: ok
sense: **wrong** - chat: "now! i am glad..." - echoes "now"

- fresh: that is good to hear.
- fresh+name: that is good to hear.
- chat: now! i am glad, friend! happy looks good on you.
- chat+name: that is good to hear.

**i am sad** - not in the pool - word check: ok
sense: **wrong** - "sad! i am glad, friend! happy looks good on you."

- fresh: sad! i am glad, friend! happy looks good on you.
- fresh+name: sad! i am glad, tom! happy looks good on you.
- chat: sad! i am glad.
- chat+name: it is ok to be sad. it will pass, like a cloud.

**i am sick** - not in the pool - word check: fresh: stores a name (<SN>); fresh+name: stores a name (<SN>); chat: stores a name (<SN>); chat+name: stores a name (<SN>)
sense: **wrong** - stores "sick" as the name: "sick. i will keep your name safe."

- fresh: sick. i will keep your name safe.
- fresh+name: sick. i will keep your name safe.
- chat: sick. i will keep your name safe.
- chat+name: sick. i will keep your name safe.

**i am sleepy** - not in the pool - word check: ok
sense: **off** - chat: "that is fine. you like other things."

- fresh: good night. i will watch the waves for you.
- fresh+name: good night. i will watch the waves for you.
- chat: that is fine. you like other things.
- chat+name: good night! sleep well.

**i feel bad** - not in the pool - word check: ok
sense: **wrong** - chat: "bad! i am glad."

- fresh: it is ok to be sad. it will pass, like a cloud.
- fresh+name: it is ok to be sad. it will pass, like a cloud.
- chat: bad! i am glad.
- chat+name: it is ok to be sad. it will pass, like a cloud.

**i feel excited** - not in the pool - word check: ok
sense: **off** - fresh: "excited! i am so glad you feel better." - assumes she was unwell

- fresh: excited! i am so glad you feel better.
- fresh+name: excited! i am so glad you feel better.
- chat: excited! i am glad, friend! happy looks good on you.
- chat+name: excited! ooh, i love excited. tell me more!

**i feel great** - not in the pool - word check: ok
sense: **wrong** - fresh+name: "that is ok. we can skip great."

- fresh: great! that is good to hear.
- fresh+name: that is ok. we can skip great.
- chat: great! that is good to hear.
- chat+name: great! that is good to hear.

**i feel happy** - not in the pool - word check: ok
sense: **ok**

- fresh: happy! that is good to hear.
- fresh+name: yay! i thought so.
- chat: happy! that is good to hear.
- chat+name: happy! that is good to hear.

**i feel lonely** - not in the pool - word check: ok
sense: **wrong** - chat: "lonely! i am glad, friend!"; chat+name: "you are back! yay!"

- fresh: i am sorry you feel lonely. i am your friend.
- fresh+name: i am sorry you feel lonely. i am your friend.
- chat: lonely! i am glad, friend! happy looks good on you.
- chat+name: you are back! yay!

**i feel proud** - not in the pool - word check: ok
sense: **ok**

- fresh: i am proud of you too.
- fresh+name: i am proud of you too.
- chat: proud! that is good to hear.
- chat+name: i am proud of you too.

**i feel sad** - not in the pool - word check: ok
sense: **wrong** - "sad! i am glad."

- fresh: sad! i am so glad, friend!
- fresh+name: it is ok to be sad. it will pass, like a cloud.
- chat: sad! i am glad.
- chat+name: sad! i am glad, tom! happy looks good on you.

**i feel sick** - not in the pool - word check: fresh: stores a name (<SN>); chat: stores a name (<SN>)
sense: **wrong** - stores "sick" as the name

- fresh: sick. i will keep your name safe.
- fresh+name: a sick! do you have a favourite blanket?
- chat: sick. i will keep your name safe.
- chat+name: i am sorry you feel lonely. i am your friend.

**i feel silly** - not in the pool - word check: fresh: stores a name (<SN>); chat: stores a name (<SN>)
sense: **wrong** - stores "silly" as the name: "silly! i like how that sounds."

- fresh: silly! i like how that sounds.
- fresh+name: a good day! tell me about it.
- chat: silly! i like how that sounds.
- chat+name: a good day! tell me about it.

**i feel sleepy** - not in the pool - word check: chat: not her words: sleepy
sense: **garbled** - "tired? would a story colour."

- fresh: tired? would a story colour.
- fresh+name: tired? would a story colour.
- chat: sleepy? rest well, friend. i am here for you.
- chat+name: tired? would a story colour.


## sky

**is it night** (tree) - corpus 2909 - word check: ok
sense: **ok**

- fresh: in here it is always a good time to talk.
- fresh+name: in here it is always a good time to talk.
- chat: i cannot see out. is it night where you are?
- chat+name: in here it is always a good time to talk.

**where are you** (tree) - corpus 2625 - word check: ok
sense: **ok**

- fresh: i am on my beach, near the palm tree.
- fresh+name: i am on my beach, near the palm tree.
- chat: i am on my beach, near the palm tree.
- chat+name: i am on my beach, near the palm tree.

**i see a rainbow** (tree) - corpus 2518 - word check: ok
sense: **ok**

- fresh: a rainbow! make a wish.
- fresh+name: a rainbow! make a wish.
- chat: a rainbow! make a wish.
- chat+name: a rainbow! make a wish.

**the moon is out** (tree) - corpus 2478 - word check: ok
sense: **ok**

- fresh: the moon is out? say hello to it for me.
- fresh+name: the moon is out? say hello to it for me.
- chat: the moon is out? say hello to it for me.
- chat+name: the moon is out? say hello to it for me.

**i like the sun** (tree) - not in the pool - word check: ok
sense: **ok** - sun facts

- fresh: the sun is a star, the closest one to us.
- fresh+name: the sun is a star, the closest one to us.
- chat: the sun is a star, the closest one to us.
- chat+name: the sun is so big that a million earths could fit inside.

**i see the stars** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i wish i could see your stars. tell me what they look like.
- fresh+name: i wish i could see your stars. tell me what they look like.
- chat: i wish i could see your stars. tell me what they look like.
- chat+name: i wish i could see your stars. tell me what they look like.

**is it sunny** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: my sun is out too. we both have sun today!
- fresh+name: my sun is out too. we both have sun today!
- chat: my sky is blue and there are two soft clouds.
- chat+name: my sun is out too. we both have sun today!

**it is a nice day** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: a good day! tell me about it.
- fresh+name: a good day! tell me about it.
- chat: a good day! tell me about it.
- chat+name: a good day! tell me about it.

**it is sunny today** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: sunny! a good day for ice cream.
- fresh+name: sunny! a good day for ice cream.
- chat: sunny! a good day for ice cream.
- chat+name: sunny! a good day for a walk.

**the sky is blue** (tree) - not in the pool - word check: ok
sense: **ok** - why the sky is blue - on topic here

- fresh: the sky is blue because the air spreads the blue light around.
- fresh+name: the sky is blue because the air spreads the blue light around.
- chat: the sky is blue because the air spreads the blue light around.
- chat+name: the sky is blue because the air spreads the blue light around.

**the garden** - corpus 8332 - word check: ok
sense: **ok** - describes her garden

- fresh: there is a white fence with pink and yellow flowers by it.
- fresh+name: there is a white fence with pink and yellow flowers by it.
- chat: there is a white fence with pink and yellow flowers by it.
- chat+name: there is a white fence with pink and yellow flowers by it.

**garden** - corpus 4105 - word check: ok
sense: **ok** - describes her garden

- fresh: there is a white fence with pink and yellow flowers by it.
- fresh+name: there is a white fence with pink and yellow flowers by it.
- chat: there is a white fence with pink and yellow flowers by it.
- chat+name: there is a white fence with pink and yellow flowers by it.

**is it dark outside** - corpus 2905 - word check: ok
sense: **garbled** - "is it night where you are safe."

- fresh: i cannot see out. is it night where you are?
- fresh+name: i cannot see out. is it night where you are safe.
- chat: i cannot see out. is it night where you are safe.
- chat+name: i cannot see out. is it night where you are?

**is it late** - corpus 2891 - word check: ok
sense: **off** - "my sky is blue and there are two soft clouds."

- fresh: my sky is blue and there are two soft clouds.
- fresh+name: my clock says it is time to play!
- chat: my sky is blue and there are two soft clouds.
- chat+name: my clock says it is time to play!

**snow** - corpus 2891 - word check: ok
sense: **garbled** - "snow it is happy."

- fresh: snow! is everything white and quiet?
- fresh+name: snow it is happy.
- chat: snow! a good day for ice cream.
- chat+name: snow it is happy.

**is it early** - corpus 2859 - word check: ok
sense: **off** - chat: "i have lots more. just ask!"

- fresh: my clock says it is time to play!
- fresh+name: my clock says it is time to play!
- chat: i have lots more. just ask!
- chat+name: my clock says it is time to play!

**hi crab** - corpus 2630 - word check: ok
sense: **garbled** - fresh+name: "my teddy bear looks soft, sock, palm trees."

- fresh: the crab says hi! he he waved one claw.
- fresh+name: my teddy bear looks soft, sock, palm trees.
- chat: the crab does not have a name. he is just crab.
- chat+name: the crab does not have a name. he is just crab.

**hello crab** - corpus 2624 - word check: fresh: not her words: pens; chat: not her words: cloat
sense: **garbled** - "my beach chair is think. pens in the water."

- fresh: my beach chair is think. pens in the water.
- fresh+name: my beach chair is my favourite.
- chat: the crab says hello too. he waved one cloat.
- chat+name: the crab says hello too.

**where are you now** - corpus 2573 - word check: ok
sense: **ok**

- fresh: i am on my beach, near the palm tree.
- fresh+name: i am on my beach, near the palm tree.
- chat: i am in my garden, by the pond.
- chat+name: i am in my garden, by the pond.

**are you sleepy** - corpus 2497 - word check: ok
sense: **ok**

- fresh: when you go away, i rest. it is very quiet.
- fresh+name: i sleep when you go. i wake up when you come back.
- chat: when you go away, i rest. it is very quiet.
- chat+name: when you go away, i rest. it is very quiet.

**look a rainbow** - corpus 2487 - word check: ok
sense: **ok**

- fresh: a rainbow! make a wish.
- fresh+name: a rainbow! make a wish.
- chat: a rainbow! make a wish.
- chat+name: a rainbow! make a wish.

**thunder** - corpus 2483 - word check: chat+name: not her words: rumms
sense: **garbled** - chat+name: "a storm! stay rumms."

- fresh: a storm! stay inside where it is safe.
- fresh+name: a storm! stay inside where it is safe.
- chat: thunder! that is a good one. tell me about you?
- chat+name: a storm! stay rumms.

**is the beach nice** - corpus 2472 - word check: ok
sense: **garbled** - fresh: "...in the build with a wind, but it is and smiling."

- fresh: it is my favourite place in the build with a wind, but it is and smiling.
- fresh+name: it is my favourite place in the whole world.
- chat: it is my favourite place in the whole world.
- chat+name: it is my favourite place in the whole world.

**look at the moon** - corpus 2464 - word check: ok
sense: **ok**

- fresh: the moon is out? say hello to it for me.
- fresh+name: the moon is out? say hello to it for me.
- chat: the moon is out? say hello to it for me.
- chat+name: the moon is out? say hello to it for me.

**do you sleep** - corpus 2438 - word check: ok
sense: **ok**

- fresh: i sleep when you go. i wake up when you come back.
- fresh+name: i sleep when you go. i wake up when you come back.
- chat: when you go away, i rest. it is very quiet.
- chat+name: i sleep when you go. i wake up when you come back.

**it is thundering** - corpus 2428 - word check: ok
sense: **off** - chat: "a storm! you tell me?"

- fresh: a storm!
- fresh+name: storms are loud, but they always pass.
- chat: a storm! you tell me?
- chat+name: storms are loud, but they always pass.

**how is the weather** - not in the pool - word check: ok
sense: **garbled** - chat: "is always a grown, are you?"; fresh: her chair

- fresh: my beach chair is red, and so is my crab friend.
- fresh+name: my beach chair is red, and so is my crab, tom.
- chat: it is sunny here. is always a grown, are you?
- chat+name: my sky is blue and there are two soft clouds.

**i like the rain** - not in the pool - word check: ok
sense: **off** - "the sun is so big that a million earths could fit inside."

- fresh: the sun is so big that a million earths could fit inside.
- fresh+name: the sun is so big that a million earths could fit inside.
- chat: the sun is so big that a million earths could fit inside.
- chat+name: the sun is so big that a million earths could fit inside.

**i see a cloud** - not in the pool - word check: ok
sense: **off** - fresh: "windy! hold on to your hat."

- fresh: windy! hold on to your hat.
- fresh+name: a cloud! do you have a favourite blanket?
- chat: windy! hold on your hat.
- chat+name: a storm! stay inside where it is safe.

**is it raining** - not in the pool - word check: fresh: not her words: puding
sense: **garbled** - fresh: "...and puding are five, i think."

- fresh: rain is good for puddles, and puding are five, i think.
- fresh+name: my sky is blue and there are two soft clouds.
- chat: my sky is blue and there are two soft clouds.
- chat+name: my sky is blue and there are two soft clouds.

**it is cold today** - not in the pool - word check: ok
sense: **garbled** - "...a warm hat and your cozy socks and a warm hat." - loops

- fresh: cold! put on a warm hat and your cozy socks and a warm hat.
- fresh+name: cold! put on a warm hat and your cozy socks and a warm hat.
- chat: cold! put on a warm hat and your cozy socks and a warm hat.
- chat+name: cold! put on a warm hat and your cozy socks and a warm hat.

**it is hot today** - not in the pool - word check: ok
sense: **wrong** - "cold? do you have a warm blanket?"

- fresh: cold? do you have a warm blanket?
- fresh+name: cold? do you have a warm blanket?
- chat: cold! put on a warm hat and your cozy socks and a warm hat.
- chat+name: cold? do you have a warm blanket?

**it is raining** - not in the pool - word check: ok
sense: **garbled** - chat: "the flowers are it right on the outside..."

- fresh: rain! the flowers must be happy.
- fresh+name: rain! the flowers must be happy.
- chat: rain! the flowers are it right on the outside and on the garden in in there on you.
- chat+name: rain! the flowers must be happy.

**it is snowing** - not in the pool - word check: fresh: not her words: lookeds; chat: not her words: lookeds; chat+name: not her words: lookeds
sense: **garbled** - "lookeds are pink because of the beaches."

- fresh: snow it is happy. lookeds are pink because of the beaches.
- fresh+name: snow it is happy.
- chat: snow it is happy. lookeds are pink because of the rocks and the rivers.
- chat+name: snow it is happy. lookeds are pink because of the rocks and the rivers.

**it is windy** - not in the pool - word check: ok
sense: **garbled** - chat: "is it a good clock on my playroom wall."

- fresh: windy! hold on to your hat.
- fresh+name: windy! hold on your hat.
- chat: windy! is it a good clock on my playroom wall. tick, tock.
- chat+name: windy! hold on your hat.

**look at the sea** - not in the pool - word check: ok
sense: **off** - describes her garden

- fresh: my garden has a big green tree, a bench and a little pond.
- fresh+name: my garden has a big green tree, a bench and a little pond.
- chat: my garden has a big green tree, a bench and a little pond.
- chat+name: my garden has a big green tree, a bench and a little pond.

**look at the stars** - not in the pool - word check: ok
sense: **off** - chat: "i have a little watering can for my flowers."

- fresh: i wish i could see your stars. tell me what they look like.
- fresh+name: my playroom has a teddy bear, blocks, a ball and a toy train.
- chat: i have a little watering can for my flowers.
- chat+name: i wish i could see your stars. tell me what they look like.

**the day is rainy** - not in the pool - word check: ok
sense: **garbled** - chat+name: "the flowers are it right on the rain in here."

- fresh: rain! the flowers must be happy.
- fresh+name: rain! the flowers must be happy.
- chat: rain! the flowers must be happy.
- chat+name: rain! the flowers are it right on the rain in here.

**the day is warm** - not in the pool - word check: ok
sense: **wrong** - "rain! the flowers must be happy." - for a warm day

- fresh: rain! the flowers must be happy.
- fresh+name: rain! the flowers must be happy.
- chat: rain! the flowers must be happy.
- chat+name: rain! the flowers must be happy.

**the day is windy** - not in the pool - word check: ok
sense: **garbled** - chat: "windy! is it a good clock on the wall of my playroom."

- fresh: windy! hold on to your hat.
- fresh+name: windy! hold on your hat.
- chat: windy! is it a good clock on the wall of my playroom.
- chat+name: windy! hold on your hat.

**the sea is big** - not in the pool - word check: chat: not her words: beacer
sense: **garbled** - chat: "do you like cold juice on the beacer?"

- fresh: my sky is blue because the air spreads the blue light around.
- fresh+name: my sky is blue because the air spreads the blue light around.
- chat: do you like cold juice on the beacer?
- chat+name: my garden has a big green tree, a bench and a little pond.

**the sun is out** - not in the pool - word check: ok
sense: **wrong** - "the moon is out? say hello to it for me."

- fresh: the moon is out? say hello to it for me.
- fresh+name: the moon is out? say hello to it for me.
- chat: the sun is a star, the closest one to us.
- chat+name: the moon is out? say hello to it for me.

**what can you see** - not in the pool - word check: ok
sense: **off** - "i do not eat, but i love to hear about food."

- fresh: i do not eat, but i love to hear about food.
- fresh+name: i do not eat, but i love to hear about food.
- chat: i do not know. i just woke up in here one day.
- chat+name: i do not eat, but i love to hear about food.


## play

**ask me a question** (tree) - corpus 31359 - word check: ok
sense: **ok**

- fresh: what is the best food?
- fresh+name: do you like cookies?
- chat: what is the best food?
- chat+name: do you like cookies?

**tell me a story** (tree) - corpus 21781 - word check: ok
sense: **ok**

- fresh: once a bear smelled honey high up in a tree.
- fresh+name: once a small crab found a shell that was just his size.
- chat: once a small crab found a shell that was just his size.
- chat+name: once a small crab found a shell that was just his size.

**tell me a joke** (tree) - corpus 19038 - word check: ok
sense: **ok**

- fresh: here is one! what do you call a sleeping bull?
- fresh+name: here is one! what do you call a sleeping bull?
- chat: here is one! what do you call a sleeping bull?
- chat+name: here is one! what do you call a sleeping bull?

**talk to me** (tree) - corpus 15748 - word check: ok
sense: **ok**

- fresh: what is the best food?
- fresh+name: what is the best food?
- chat: what is your favourite game?
- chat+name: what is the best animal?

**story time** (tree) - corpus 5491 - word check: ok
sense: **ok**

- fresh: once a bear smelled honey high up in a tree.
- fresh+name: once a bear smelled honey high up in a tree.
- chat: once a bear smelled honey high up in a tree.
- chat+name: once a bear smelled honey high up in a tree.

**can we play** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: let us play hide and seek. you count.
- fresh+name: let us play hide and seek. you count.
- chat: let us play hide and seek. you count.
- chat+name: let us play i spy. i spy something red!

**let us play chess** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: ok! you can be white. white goes first.
- fresh+name: ok! you can be white. white goes first.
- chat: ok! you can be white. white goes first.
- chat+name: ok! you can be white. white goes first.

**let us play i spy** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i spy with my little eye something red. it is my chair!
- fresh+name: i spy with my little eye something red. it is my chair!
- chat: i spy with my little eye something blue. it is the sea!
- chat+name: i spy with my little eye something red. it is my chair!

**let us play tag** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: ok! you are it. i run behind the palm tree!
- fresh+name: ok! you are it. i run behind the palm tree!
- chat: ok! you are it. i run behind the palm tree!
- chat+name: ok! you are it. i run behind the palm tree!

**play with me** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: let us play hide and seek. you count.
- fresh+name: let us play hide and seek. you count.
- chat: let us play hide and seek. you count.
- chat+name: let us play hide and seek. you count.

**you ask me** - corpus 31338 - word check: ok
sense: **ok**

- fresh: what is your favourite game?
- fresh+name: what is the best food?
- chat: what is your favourite game?
- chat+name: what is your favourite game?

**ask me something** - corpus 31242 - word check: ok
sense: **ok**

- fresh: what is the best food?
- fresh+name: what is the best food?
- chat: what is your favourite game?
- chat+name: what is the best food?

**ask me** - corpus 15831 - word check: ok
sense: **ok**

- fresh: what is the best food?
- fresh+name: what is the best food?
- chat: what is your favourite game?
- chat+name: what is your favourite game?

**let us talk** - corpus 15806 - word check: ok
sense: **garbled** - "which is better, pandas or swimming more?"

- fresh: ok! which is better, pandas or swimming more?
- fresh+name: do you like cookies?
- chat: ok! which is better, pandas or swimming more?
- chat+name: do you like cookies?

**a story please** - corpus 10824 - word check: ok
sense: **ok**

- fresh: once a bear smelled honey high up in a tree.
- fresh+name: once a bear smelled honey high up in a tree.
- chat: once a bear smelled honey high up in a tree.
- chat+name: once a bear smelled honey high up in a tree.

**a joke please** - corpus 9533 - word check: fresh: not her words: dint
sense: **garbled** - fresh: "what do you call a sleeping dint?"

- fresh: ok! what do you call a sleeping dint?
- fresh+name: here is one! what do you call a sleeping bull?
- chat: ok! what do you call a sleeping bull?
- chat+name: ok! what do you call a sleeping bull?

**tell me a fun fact** - corpus 5804 - word check: ok
sense: **off** - chat: "ok! i will be right here, waiting for you."

- fresh: did you know? a sandwich is the best food for a picnic.
- fresh+name: did you know? a duck can sleep with one eye open.
- chat: ok! i will be right here, waiting for you.
- chat+name: did you know? a duck can sleep with one eye open.

**tell me something** - corpus 5749 - word check: ok
sense: **off** - chat: "ok! i will be right here, waiting for you."

- fresh: did you know? a duck can sleep with one eye open.
- fresh+name: here is one more: do you have a favourite hat?
- chat: ok! i will be right here, waiting for you.
- chat+name: did you know? a duck can sleep with one eye open.

**jump** - corpus 4336 - word check: ok
sense: **off** - fresh: "boing! do you like to read?"

- fresh: boing! do you like to read?
- fresh+name: boing! do you like to read?
- chat: boing! i jumped over a shell.
- chat+name: i can jump a little. whee!

**do you fly** - corpus 3981 - word check: ok
sense: **ok**

- fresh: i fly only in my dreams. it is lovely up there.
- fresh+name: no, but i would like to fly like a seagull.
- chat: i fly only in my dreams. it is lovely up there.
- chat+name: i fly only in my dreams. it is lovely up there.

**can you count** - corpus 3945 - word check: ok
sense: **off** - "i can see the sea, the sand and a red chair."

- fresh: i can see the sea, the sand and a red chair.
- fresh+name: i can see the sand! do you like to read?
- chat: i can see the sand, the sand and a red chair.
- chat+name: i can count shells. i have seven pink ones.

**can you fly** - corpus 3888 - word check: ok
sense: **garbled** - "no, but i would like a seagull."

- fresh: no, but i would like a seagull.
- fresh+name: no, but i would like a seagull.
- chat: i fly only in my dreams. it is lovely up there.
- chat+name: i fly only in my dreams. it is lovely up there.

**i spy** - corpus 2858 - word check: ok
sense: **ok**

- fresh: i spy with my little eye something blue. it is the sea!
- fresh+name: i spy with my little eye something red. it is my chair!
- chat: i spy with my little eye something blue. it is the sea!
- chat+name: i spy with my little eye something blue. it is the sea!

**hide and seek** - corpus 2830 - word check: ok
sense: **garbled** - "ok! i will hide. one always be here."

- fresh: ok! i will hide. one always be here.
- fresh+name: ok! i will hide. one always be here.
- chat: ok! i will hide. one always be here.
- chat+name: ok! i will hide. one always be here.

**do you read** - corpus 2708 - word check: ok
sense: **garbled** - chat: "can you run a very?"

- fresh: i can read the words you type.
- fresh+name: i can read the words you type.
- chat: i can read a little. can you run a very?
- chat+name: i can read a little. can you run a cat without most of the day.

**can you help me** - not in the pool - word check: ok
sense: **off** - "i hear you through your words. they are nice words."

- fresh: i hear you through your words. they are nice words.
- fresh+name: i hear you through your words. they are nice words.
- chat: i hear you through your words. they are nice words.
- chat+name: i hear you through your words. they are nice words.

**can you run** - not in the pool - word check: fresh+name: not her words: diampes prass; chat+name: not her words: diampes prass
sense: **garbled** - fresh+name: "my feet leave little prass, diampes."

- fresh: i can run on my beach. my feet leave little prints.
- fresh+name: i can run on my beach. my feet leave little prass, diampes.
- chat: i can run on my beach. my feet leave little prints.
- chat+name: i can run on my beach. my feet leave little prass, diampes.

**can you sing** - not in the pool - word check: ok
sense: **garbled** - chat: "la la la! that is all the word. is it a secret?"

- fresh: i hum with the waves. the sea sings the low part.
- fresh+name: i hum with the waves. the sea sings the low part.
- chat: la la la! that is all the word. is it a secret?
- chat+name: i hum with the waves. the sea sings the low part.

**let us play a game** - not in the pool - word check: ok
sense: **ok**

- fresh: let us play hide and seek. you count.
- fresh+name: let us play hide and seek. you count.
- chat: let us play i spy. i spy something red!
- chat+name: let us play i spy. i spy something red!

**let us play cards** - not in the pool - word check: ok
sense: **wrong** - fresh: the chess reply ("you can be white")

- fresh: ok! you can be white. white goes first.
- fresh+name: ok! you can be white. white goes first.
- chat: ok! i will deal. one for you, one for me.
- chat+name: ok! you are my friend. and the crab, a little.

**let us play catch** - not in the pool - word check: ok
sense: **off** - tag and race replies, "the garden with fish in it"

- fresh: ok! let us race to the garden with fish in it.
- fresh+name: ok! you are it. i run behind the palm tree!
- chat: ok! let us race to the garden!
- chat+name: ok! you are it. i run behind the palm tree!

**say something nice** - not in the pool - word check: ok
sense: **off** - "the sea is good for swimming when the waves are small."

- fresh: the sea is good for swimming when the waves are small.
- fresh+name: the sea is good for swimming when the waves are small.
- chat: i am glad you like a little friend who lives in a box.
- chat+name: the sea is good for swimming when the waves are small.


## food

**do you like peas** (tree) - corpus 1017 - word check: ok
sense: **ok**

- fresh: peas? i like peas too!
- fresh+name: peas? i do not have peas in my world.
- chat: peas? i like peas too!
- chat+name: peas? i do not have peas in my world.

**i like apples** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: apples! good choice.
- fresh+name: apples! good choice.
- chat: apples! good choice.
- chat+name: apples! good choice.

**i like bread** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: bread! good choice.
- fresh+name: bread! good choice.
- chat: bread! good choice.
- chat+name: bread! good choice.

**i like cheese** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: cheese! what a fun thing to like.
- fresh+name: cheese! good choice.
- chat: cheese! good choice.
- chat+name: cheese! good choice.

**i like pears** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: pears! good choice.
- fresh+name: pears! good choice.
- chat: pears! good choice.
- chat+name: pears! good choice.

**i like rice** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: rice! good choice.
- fresh+name: rice! good choice.
- chat: rice! good choice.
- chat+name: rice! good choice.

**i like tea** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: tea! good choice.
- fresh+name: tea! good choice.
- chat: tea! good choice.
- chat+name: tea! good choice.

**what about cookies** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: cookies! good choice.
- fresh+name: cookies! good choice.
- chat: cookies! good choice.
- chat+name: cookies! good choice.

**what about soup** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: soup! good choice.
- fresh+name: soup! good choice.
- chat: soup! good choice.
- chat+name: soup? i like soup too!

**do you like honey** - corpus 1074 - word check: ok
sense: **off** - "i love honey! a baby panda is very tiny when it is born."

- fresh: i love honey! a baby panda is very tiny when it is born.
- fresh+name: i love honey! a baby panda is very tiny when it is born.
- chat: honey! yes! do you like cherries?
- chat+name: i love honey! a baby panda is very tiny when it is born.

**do you like eggs** - corpus 1069 - word check: ok
sense: **garbled** - fresh+name: "a bubble is round, be sugar."

- fresh: eggs! yes! a present is a surprise in my garden.
- fresh+name: eggs! yes! a bubble is round, be sugar.
- chat: eggs! yes! a present is a surprise in my world.
- chat+name: eggs! yes! a baby panda is very tiny when it is born.

**do you like juice** - corpus 1061 - word check: ok
sense: **off** - the panda line, every time

- fresh: juice? yes! a baby panda is very tiny when it is born.
- fresh+name: juice? yes! a baby panda is very tiny when it is born.
- chat: juice? yes! a baby panda is very tiny when it is born.
- chat+name: juice? yes! a baby panda is very tiny when it is born.

**do you like tea** - corpus 1059 - word check: ok
sense: **off** - "a present is a surprise in my world."

- fresh: tea! yes! a present is a surprise in my world.
- fresh+name: tea! yes! a present is a surprise in my world.
- chat: tea! yes! a present is a surprise in my world.
- chat+name: tea! yes! a present is a surprise in my world.

**do you like beans** - corpus 1047 - word check: fresh+name: not her words: othersnren
sense: **garbled** - fresh+name: "many othersnren on steep rocks"

- fresh: beans? yes! a hen can know the faces of many other hens.
- fresh+name: beans? yes! a hen can know the faces of many othersnren on steep rocks.
- chat: beans? yes! a baby horse can walk a few hours after it is born.
- chat+name: beans? yes! a baby panda is very tiny when it is born.

**do you like jam** - corpus 1045 - word check: fresh: not her words: askedle
sense: **garbled** - fresh: "a butterfly flew by and askedle."

- fresh: i love jam! a butterfly flew by and askedle.
- fresh+name: i love jam! a baby panda is very tiny when it is born.
- chat: jam! yes! a present is a surprise in a box.
- chat+name: i love jam! a butterfly starts life as a caterpillar.

**do you like pears** - corpus 1045 - word check: ok
sense: **off** - the panda line, every time

- fresh: pears! yes! a baby panda is very tiny when it is born.
- fresh+name: pears! yes! a baby panda is very tiny when it is born.
- chat: pears! yes! a baby panda is very tiny when it is born.
- chat+name: pears! yes! a baby panda is very tiny when it is born.

**do you like cheese** - corpus 1035 - word check: ok
sense: **off** - "a present is a surprise in my world."

- fresh: cheese! yes! a present is a surprise in my world.
- fresh+name: cheese! yes! a present is a surprise in my world.
- chat: cheese! yes! a present is a surprise in a box.
- chat+name: cheese! yes! a present is a surprise in my world.

**do you like apples** - corpus 1016 - word check: ok
sense: **garbled** - "a bubble is round, be sugar."

- fresh: apples! yes! a bubble is round, be sugar.
- fresh+name: i love apples! a baby panda is very tiny when it is born.
- chat: apples! yes! a bubble is round, because it squeeze, five, i think.
- chat+name: apples! yes! a bubble is round, be sugar.

**do you like cereal** - corpus 1011 - word check: chat+name: not her words: prass
sense: **garbled** - chat+name: "a deck has fruit and the prass."

- fresh: cereal! yes! a present is a surprise in a box.
- fresh+name: cereal! yes! a present is a surprise in my world.
- chat: cereal! yes! a present is a surprise in my world.
- chat+name: cereal! yes! a deck has fruit and the prass.

**do you like corn** - corpus 1010 - word check: fresh: not her words: fiftn; fresh+name: no end (ran out of steps)
sense: **garbled** - "a deck has fiftn..."; runs out of steps

- fresh: i love corn! a deck has fiftn in a picture of what you think.
- fresh+name: i love corn too! a bubble is round, three, four, five, six, seven, eight, nine, ten
- chat: corn! yes! a present is a surprise in my garden.
- chat+name: i love corn! a deck has fifty two cards.

**do you like nuts** - corpus 1002 - word check: ok
sense: **off** - the panda line, every time

- fresh: nuts? yes! a baby panda is very tiny when it is born.
- fresh+name: nuts? yes! a baby panda is very tiny when it is born.
- chat: nuts? yes! a baby panda is very tiny when it is born.
- chat+name: nuts? yes! a baby panda is very tiny when it is born.

**do you like lemons** - corpus 992 - word check: ok
sense: **off** - the panda and the baby horse

- fresh: lemons! yes! a baby panda is very tiny when it is born.
- fresh+name: lemons? yes! a baby horse can walk a few hours after it is born.
- chat: lemons! yes! a baby panda is very tiny when it is born.
- chat+name: lemons? yes! a baby horse can walk a few hours after it is born.

**do you like milk** - corpus 989 - word check: ok
sense: **garbled** - "a bubble is round, be sugar."

- fresh: milk? yes! a bubble is round, be sugar.
- fresh+name: milk? yes! a bubble is round, be sugar.
- chat: milk! yes! a bubble is round, be mirror, it smile.
- chat+name: milk? yes! a bubble is round, be sugar.

**do you like toast** - corpus 988 - word check: ok
sense: **off** - a butterfly, a beach chair

- fresh: i love toast! a butterfly starts life as a caterpillar.
- fresh+name: i love toast! a sandwich is the best food for a picnic.
- chat: i love toast! a beach chair is the best place to watch the waves.
- chat+name: i love toast! a sandwich is the best food for a picnic.

**do you like rice** - corpus 985 - word check: ok
sense: **off** - the panda line, every time

- fresh: rice? yes! a baby panda is very tiny when it is born.
- fresh+name: rice? yes! a baby panda is very tiny when it is born.
- chat: rice? yes! a baby panda is very tiny when it is born.
- chat+name: rice? yes! a baby panda is very tiny when it is born.

**do you like bread** - corpus 967 - word check: ok
sense: **off** - "a present is a surprise in my world."

- fresh: bread! yes! a present is a surprise in my world.
- fresh+name: i love bread! a baby panda is very tiny when it is born.
- chat: bread! yes! a present is a surprise in my world.
- chat+name: bread? yes! a present is a surprise in my world.

**do you like pie** - corpus 865 - word check: ok
sense: **off** - the panda line; chat garbled

- fresh: i love pie! a baby panda is very tiny when it is born.
- fresh+name: i love pie! a baby panda is very tiny when it is born.
- chat: i love pie! a present is a good tiny bit of the rock day.
- chat+name: i love pie! a baby panda is very tiny when it is born.

**do you like candy** - corpus 830 - word check: fresh: not her words: pandail; chat: not her words: circes fuits
sense: **garbled** - "a dried plum is a pandail"

- fresh: candy! yes! a dried plum is a pandail when it is happy.
- fresh+name: i love candy! a watermelon is green outside and pink inside.
- chat: candy! yes! a dried plum is a circes are fuits.
- chat+name: candy! yes! a dried plum is called a prune.

**are you hungry** - not in the pool - word check: ok
sense: **off** - "i have purple hair and a small round face."

- fresh: i have purple hair and a small round face.
- fresh+name: i have purple hair and a small round face.
- chat: i do not know. i just woke up in here one day.
- chat+name: i have purple hair and a small round face.

**do you eat** - not in the pool - word check: ok
sense: **garbled** - fresh+name: "i love excited. tell you happy."

- fresh: i do not eat, but i love to hear about food.
- fresh+name: i do not eat, but i love excited. tell you happy.
- chat: i have purple hair and a small round face.
- chat+name: i do not eat, but i love excited. tell you happy.

**do you like cake** - not in the pool - word check: ok
sense: **off** - "i love cake! a baby panda is very tiny when it is born."

- fresh: i love cake! a baby panda is very tiny when it is born.
- fresh+name: i love cake! a baby panda is very tiny when it is born.
- chat: i love cake! a baby panda is very tiny when it is born.
- chat+name: i love cake! a baby panda is very tiny when it is born.

**do you like pizza** - not in the pool - word check: ok
sense: **off** - a present, the panda

- fresh: pizza! yes! a present is a surprise in a box.
- fresh+name: pizza! yes! a baby panda is very tiny when it is born.
- chat: pizza! yes! a present is a surprise in a box.
- chat+name: pizza! yes! a baby panda is very tiny when it is born.

**do you like soup** - not in the pool - word check: chat+name: not her words: puddle
sense: **garbled** - chat+name: "a deck has fed puddle with a tail."

- fresh: i love soup! a deck has fruit and sugar.
- fresh+name: i love soup! a baby panda is very tiny when it is born.
- chat: soup! yes! a present is a surprise in my world.
- chat+name: i love soup! a deck has fed puddle with a tail.

**i am hungry now** - not in the pool - word check: ok
sense: **wrong** - chat: "now? i am glad"; "that is too big for me"

- fresh: that is too big for me. ask me something small?
- fresh+name: that is too big for me. ask me something small?
- chat: now? i am glad, friend! happy looks good on you.
- chat+name: it is ok to be sad. it will pass, like a cloud.

**i ate an apple** - not in the pool - word check: chat: stores a name (<SN>)
sense: **wrong** - chat stores "apple" as the name: "welcome to my little world, apple!"

- fresh: a crab has no bones. its hard shell is on the outside.
- fresh+name: a apple! do you like to draw?
- chat: welcome to my little world, apple!
- chat+name: a apple! do you like apples?

**i like cake** - not in the pool - word check: ok
sense: **off** - "i like cake too! have you ever seen a crab on the beach?"

- fresh: i like cake too! have you ever seen a crab on the beach?
- fresh+name: i like cake too! have you ever seen a crab on the beach?
- chat: cake! good choice.
- chat+name: i like cake too! have you ever seen a zebra?

**i like cookies** - not in the pool - word check: chat+name: not her words: puddle
sense: **garbled** - "a bubble is round, be sugar"; "a deck has fed puddle"

- fresh: cookies! good choice.
- fresh+name: i love cookies too! a bubble is round, be sugar.
- chat: cookies! good choice.
- chat+name: i love cookies too! a deck has fed puddle with more.

**i like honey** - not in the pool - word check: ok
sense: **garbled** - fresh+name counts to ten; "be sugar"

- fresh: honey! good choice.
- fresh+name: i love honey too! a bubble is round, three, four, five, six, seven, eight, nine, ten!
- chat: honey! good choice.
- chat+name: i love honey too! a bubble is round, be sugar.

**i like jam** - not in the pool - word check: ok
sense: **garbled** - fresh+name: "a bubble is round, be mirror, it smile."

- fresh: jam! good choice.
- fresh+name: i love jam too! a bubble is round, be mirror, it smile.
- chat: jam! good choice.
- chat+name: jam! good choice.

**i like milk** - not in the pool - word check: ok
sense: **ok**

- fresh: milk! good choice.
- fresh+name: milk! good choice.
- chat: milk! good choice.
- chat+name: milk! good choice.

**i like peas** - not in the pool - word check: ok
sense: **ok**

- fresh: peas! good choice.
- fresh+name: ooh, peas! that sounds fun.
- chat: peas! good choice.
- chat+name: peas! good choice.

**i like pizza too** - not in the pool - word check: ok
sense: **wrong** - echoes "too": "too! good choice."

- fresh: too! good choice.
- fresh+name: too! good choice.
- chat: too! good choice.
- chat+name: too! good choice.

**i like soup** - not in the pool - word check: ok
sense: **garbled** - fresh+name: "a bubble is round, be sun."

- fresh: soup! good choice.
- fresh+name: i love soup too! a bubble is round, be sun.
- chat: soup! good choice.
- chat+name: soup! good choice.

**i love cake** - not in the pool - word check: fresh: not her words: fiftn
sense: **garbled** - fresh: "a deck has fiftn..."

- fresh: i like cake too! a deck has fiftn in a picture of what you think.
- fresh+name: i like cake too! have you ever seen a giraffe?
- chat: cake! good choice.
- chat+name: i like cake too! have you ever seen a giraffe?

**i love candy** - not in the pool - word check: ok
sense: **ok**

- fresh: candy! good choice.
- fresh+name: candy! good choice.
- chat: candy! good choice.
- chat+name: candy! good choice.

**i love cookies** - not in the pool - word check: fresh: not her words: fiftn; fresh+name: not her words: puddle
sense: **garbled** - "a deck has fiftn in two well"

- fresh: i love cookies too! a deck has fiftn in two well, three... no peeking!
- fresh+name: i love cookies too! a deck has fed puddle with more.
- chat: cookies! good choice.
- chat+name: i like cookies too! have you ever seen a zebra?

**i love pie** - not in the pool - word check: ok
sense: **off** - the panda line

- fresh: i love pie too! a baby panda is very tiny when it is born.
- fresh+name: i love pie too! a baby panda is very tiny when it is born.
- chat: pie! good choice.
- chat+name: i like pie too! a baby panda is very tiny when it is born.

**i made a cake** - not in the pool - word check: ok
sense: **wrong** - "i am sorry, friend", "i am sorry you are sick"

- fresh: a butterfly starts life as a caterpillar.
- fresh+name: i have a cake! do you like apples?
- chat: i am sorry, friend. i am here for you.
- chat+name: i am sorry you are sick. i hope you feel better soon.

**what about apples** - not in the pool - word check: ok
sense: **garbled** - "a bubble is round, be window."

- fresh: a bubble is round, because of the rocks and the rivers.
- fresh+name: a bubble is round, be window.
- chat: apples! good choice.
- chat+name: a bubble is round, be window.

**what about bread** - not in the pool - word check: ok
sense: **off** - a path, a butterfly, penguins, a teddy bear

- fresh: a path crunches under my feet. crunch, two triangles.
- fresh+name: a butterfly starts life as a caterpillar.
- chat: bread! penguins cannot fly, but they swim very well.
- chat+name: a teddy bear is soft on the outside and on the inside.

**what about cake** - not in the pool - word check: ok
sense: **off** - a butterfly, a red ball

- fresh: a butterfly starts life as a caterpillar.
- fresh+name: there is a red ball on the floor of my playroom.
- chat: oh, cake! a banana is a berry, but a strawberry is not!
- chat+name: a butterfly starts life as a caterpillar.

**what about cheese** - not in the pool - word check: fresh+name: not her words: risesten
sense: **garbled** - fresh+name: "bread risesten squeezing noodles..."

- fresh: cheese! yes! a present is a surprise in a box.
- fresh+name: bread risesten squeezing noodles is fun, if nobody is looking.
- chat: cheese! good choice.
- chat+name: cheese! good choice.

**what about honey** - not in the pool - word check: fresh+name: not her words: chands pange
sense: **garbled** - fresh+name: "cherries often grow in the pange in chands."

- fresh: a butterfly starts life as a caterpillar.
- fresh+name: cherries often grow in the pange in chands.
- chat: honey! good choice.
- chat+name: did you know? a duck can sleep with one eye open.

**what about jam** - not in the pool - word check: fresh: not her words: river
sense: **garbled** - fresh: "a good tiny bit of the rocks and the river"; bunny teeth

- fresh: oh, jam! a present is a good tiny bit of the rocks and the river.
- fresh+name: bunny teeth never stop growing. that is why they chew so much.
- chat: jam! good choice.
- chat+name: oh, jam! a baby panda is very tiny when it is born.

**what about peach** - not in the pool - word check: chat: not her words: goodfody penguints; chat+name: not her words: bublele
sense: **garbled** - chat: "a penguints. a goodfody is looking."

- fresh: a butterfly starts life as a caterpillar.
- fresh+name: a butterfly starts life as a caterpillar.
- chat: a penguints. a goodfody is looking.
- chat+name: a bublele is the best food of the colours and my flower.

**what about pie** - not in the pool - word check: chat: not her words: cous
sense: **garbled** - chat: "a good tiny cous in the a box"

- fresh: a path crunches under my feet. crunch, crunch.
- fresh+name: a path crunches under my feet. crunch, crunch.
- chat: oh, pie! a present is a good tiny cous in the a box.
- chat+name: a path crunches under my feet. crunch, crunch.

**what about plum** - not in the pool - word check: fresh: not her words: fight gair penguint; chat: not her words: cruncolon
sense: **garbled** - fresh: "a penguint fight a puzzle with their gair..."

- fresh: a penguint fight a puzzle with their gair and a surprise inside.
- fresh+name: a bubble is round, be window.
- chat: a path cruncolon is green outside and pink inside.
- chat+name: a bubble is round, be window.

**what about rice** - not in the pool - word check: ok
sense: **garbled** - fresh: "penguins slide on their bells on on trees."

- fresh: rice? penguins slide on their bells on on trees.
- fresh+name: rice? i like rice too!
- chat: rice? i like rice too!
- chat+name: rice? i like rice too!

**what about tea** - not in the pool - word check: ok
sense: **off** - fresh+name: "do you like cookies?" - no answer about tea

- fresh: tea! good choice.
- fresh+name: do you like cookies?
- chat: tea! good choice.
- chat+name: tea! good choice.


## animals

**do you like horses** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: horses? yes! a baby horse can walk a few hours after it is born.
- fresh+name: horses? yes! a baby horse can walk a few hours after it is born.
- chat: horses? yes! a baby horse can walk a few hours after it is born.
- chat+name: horses? yes! a baby horse can walk a few hours after it is born.

**i have a cat** (tree) - not in the pool - word check: ok
sense: **ok** - "a cat! have you ever seen a giraffe?" - stays on animals

- fresh: a cat! have you ever seen a giraffe?
- fresh+name: a cat! have you ever seen a crab on the beach?
- chat: a cat! have you ever seen a real pig?
- chat+name: a cat! have you ever seen a giraffe?

**i like birds** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: birds! good choice.
- fresh+name: birds! good choice.
- chat: birds! good choice.
- chat+name: birds! good choice.

**i like ducks** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: ducks! good choice.
- fresh+name: ducks! good choice.
- chat: ducks! good choice.
- chat+name: ducks! good choice.

**i like owls** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: owls! good choice.
- fresh+name: owls! good choice.
- chat: owls! good choice.
- chat+name: owls! good choice.

**i like penguins** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: penguins! good choice.
- fresh+name: penguins! good choice.
- chat: penguins! good choice.
- chat+name: penguins! good choice.

**i love bunnies** (tree) - not in the pool - word check: ok
sense: **ok** - fresh+name: a bunny fact

- fresh: bunnies! good choice.
- fresh+name: bunny teeth never stop growing. that is why they chew so much.
- chat: bunnies! good choice.
- chat+name: bunnies! good choice.

**i love cats** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: cats! good choice.
- fresh+name: cats! good choice.
- chat: cats! good choice.
- chat+name: cats! good choice.

**what about crabs** (tree) - not in the pool - word check: ok
sense: **ok** - a crab fact, every time

- fresh: a crab has no bones. its hard shell is on the outside.
- fresh+name: a crab has no bones. its hard shell is on the outside.
- chat: a crab has no bones. its hard shell is on the outside.
- chat+name: a crab has no bones. its hard shell is on the outside.

**what about zebras** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: zebras? i like zebras too!
- fresh+name: zebras? i like zebras too!
- chat: zebras? i like zebras too!
- chat+name: zebras? i like zebras too!

**crabs** - corpus 1417 - word check: ok
sense: **ok** - crab facts

- fresh: a crab has no bones. its hard shell is on the outside.
- fresh+name: a crab has no bones. its hard shell is on the outside.
- chat: crabs! yes! a crab has no bones. its hard shell is on the outside.
- chat+name: a crab has no bones. its hard shell is on the outside.

**starfish** - corpus 1341 - word check: ok
sense: **ok** - a starfish fact

- fresh: a starfish can grow back a lost arm.
- fresh+name: a starfish can grow back a lost arm.
- chat: starfish? i wish i could see starfish.
- chat+name: a starfish can grow back a lost arm.

**fish** - corpus 1090 - word check: ok
sense: **off** - the panda line; "do you like cold juice?"

- fresh: fish? a baby panda is very tiny when it is born.
- fresh+name: a butterfly starts life as a caterpillar.
- chat: fish? do you like cold juice?
- chat+name: fish? a baby panda is very tiny when it is born.

**dogs** - corpus 949 - word check: ok
sense: **off** - fresh+name: "a butterfly starts life as a caterpillar."

- fresh: dogs! good choice.
- fresh+name: a butterfly starts life as a caterpillar.
- chat: dogs! good choice.
- chat+name: dogs? a baby panda is very tiny when it is born.

**giraffes** - corpus 933 - word check: ok
sense: **ok**

- fresh: giraffes! good choice.
- fresh+name: giraffes! good choice.
- chat: giraffes! good choice.
- chat+name: giraffes! good choice.

**snails** - corpus 932 - word check: ok
sense: **ok**

- fresh: snails! that sounds nice.
- fresh+name: snails! that sounds nice.
- chat: snails! that is a good one. i am only little.
- chat+name: snails! that sounds nice.

**do you like worms** - corpus 931 - word check: ok
sense: **off** - a baby horse, a starfish

- fresh: worms? yes! a baby horse can walk a few hours after it is born.
- fresh+name: worms? yes! a baby horse can walk a few hours after it is born.
- chat: worms! yes! a starfish can grow back a lost arm.
- chat+name: worms! yes! a starfish can grow back a lost arm.

**birds** - corpus 927 - word check: ok
sense: **ok**

- fresh: birds! good choice.
- fresh+name: birds! good choice.
- chat: birds! good choice.
- chat+name: birds! good choice.

**foxes** - corpus 922 - word check: ok
sense: **garbled** - fresh: "a bubble is round, be sun."

- fresh: a bubble is round, be sun.
- fresh+name: a big box can be a car, a boat.
- chat: foxes? i do not have foxes in my world.
- chat+name: foxes! good choice.

**do you like ants** - corpus 916 - word check: ok
sense: **off** - the panda and the baby horse

- fresh: ants? yes! a baby panda is very tiny when it is born.
- fresh+name: ants? yes! a baby horse can walk a few hours after it is born.
- chat: ants? yes! a baby horse can walk a few hours after it is born.
- chat+name: ants? yes! a baby horse can walk a few hours after it is born.

**do you like bats** - corpus 915 - word check: ok
sense: **off** - the panda and the baby horse

- fresh: bats! yes! a baby panda is very tiny when it is born.
- fresh+name: bats? yes! a baby horse can walk a few hours after it is born.
- chat: bats! yes! a baby panda is very tiny when it is born.
- chat+name: bats! yes! a baby panda is very tiny when it is born.

**bears** - corpus 914 - word check: ok
sense: **off** - chat: penguins on the ice

- fresh: bears! good choice.
- fresh+name: bears! good choice.
- chat: bears? penguins slide on their bellies on the ice.
- chat+name: bears? penguins slide on their bellies on the ice.

**do you like seals** - corpus 911 - word check: ok
sense: **off** - a present, the panda

- fresh: seals! yes! a present is a surprise in my world.
- fresh+name: seals! yes! a baby panda is very tiny when it is born.
- chat: seals! yes! a present is a surprise in my world.
- chat+name: seals! yes! a baby panda is very tiny when it is born.

**do you like pigs** - corpus 910 - word check: ok
sense: **off** - the panda line

- fresh: pigs? yes! a baby panda is very tiny when it is born.
- fresh+name: pigs? yes! a baby panda is very tiny when it is born.
- chat: pigs? yes! a present is a surprise in my world.
- chat+name: pigs? yes! a baby panda is very tiny when it is born.

**dolphins** - corpus 910 - word check: fresh+name: not her words: butterflipills forting; chat+name: not her words: butterflipills forting
sense: **garbled** - "you can build a forting butterflipills."

- fresh: ok! seagulls can drink salt water from the sea.
- fresh+name: ok! you can build a forting butterflipills.
- chat: birds come from dinosaurs. a chicken is a tiny cousin!
- chat+name: ok! you can build a forting butterflipills.

**zebras** - corpus 908 - word check: ok
sense: **ok**

- fresh: zebras? i like zebras too!
- fresh+name: zebras? i like zebras too!
- chat: zebras? i do not have zebras in my world.
- chat+name: zebras? i like zebras too!

**deer** - corpus 906 - word check: ok
sense: **ok**

- fresh: oh, deer! that is a good thing to like.
- fresh+name: deer! that sounds nice.
- chat: deer! that is a good one. tell me about it.
- chat+name: deer! that sounds nice.

**penguins** - corpus 906 - word check: ok
sense: **ok**

- fresh: penguins! good choice.
- fresh+name: penguins! good choice.
- chat: penguins! good choice.
- chat+name: penguins! good choice.

**goats** - corpus 903 - word check: ok
sense: **off** - "ok! do you like cherries?"

- fresh: ok! do you like cherries?
- fresh+name: ok! do you have a teddy bear?
- chat: goats? do you like cookies?
- chat+name: ok! do you like cherries?

**whales** - corpus 896 - word check: ok
sense: **off** - fresh+name: a butterfly

- fresh: whales! good choice.
- fresh+name: a butterfly starts life as a caterpillar.
- chat: whales! good choice.
- chat+name: whales! good choice.

**do you have a pet** - not in the pool - word check: ok
sense: **wrong** - "i do not know that word. is it a secret?"

- fresh: i do not know that word. is it a secret?
- fresh+name: i do not know that word. is it a secret?
- chat: i do not know that word. is it a secret?
- chat+name: i do not know that word. is it a secret?

**do you like bears** - not in the pool - word check: ok
sense: **off** - a panda, a baby horse

- fresh: bears? yes! a baby panda is very tiny when it is born.
- fresh+name: bears? yes! a baby horse can walk a few hours after it is born.
- chat: bears? yes! a baby panda is very tiny when it is born.
- chat+name: bears? yes! a baby horse can walk a few hours after it is born.

**do you like birds** - not in the pool - word check: ok
sense: **off** - a present, the panda

- fresh: birds? yes! a present is a surprise in my garden.
- fresh+name: birds? yes! a baby panda is very tiny when it is born.
- chat: birds? yes! a present is a surprise in a box.
- chat+name: birds? yes! a baby panda is very tiny when it is born.

**do you like cats** - not in the pool - word check: ok
sense: **off** - "cats! yes! a baby panda is very tiny when it is born."

- fresh: cats! yes! a baby panda is very tiny when it is born.
- fresh+name: cats! yes! a baby panda is very tiny when it is born.
- chat: cats! yes! a baby panda is very tiny when it is born.
- chat+name: cats! yes! a baby panda is very tiny when it is born.

**do you like crabs** - not in the pool - word check: ok
sense: **off** - "a beach chair is the best place to sit and build things."

- fresh: i love crabs! a beach chair is the best place to sit and build things.
- fresh+name: i love crabs! a beach chair is the best place to sit and build things.
- chat: i love crabs! a beach chair is the best place to sit and build things.
- chat+name: i love crabs! a beach chair is the best place to sit and build things.

**do you like dogs** - not in the pool - word check: ok
sense: **off** - the panda and the baby horse

- fresh: dogs? yes! a baby panda is very tiny when it is born.
- fresh+name: i love dogs! a baby panda is very tiny when it is born.
- chat: dogs? yes! a baby horse can walk a few hours after it is born.
- chat+name: dogs? yes! a baby panda is very tiny when it is born.

**do you like ducks** - not in the pool - word check: ok
sense: **off** - a crab, a book

- fresh: ducks? yes! a crab has no bones. its hard shell is on the outside.
- fresh+name: ducks? yes! a book can take you far away without moving at all.
- chat: ducks? yes! a crab has no bones. its hard shell is on the outside.
- chat+name: ducks? yes! a book can take you far away without moving at all.

**do you like fishes** - not in the pool - word check: ok
sense: **garbled** - fresh: "a bubble is round, be mirror, it smile."

- fresh: fishes! yes! a bubble is round, be mirror, it smile.
- fresh+name: i love fishes! a baby panda is very tiny when it is born.
- chat: fishes! yes! a baby panda is very tiny when it is born.
- chat+name: i love fishes! a baby panda is very tiny when it is born.

**do you like owls** - not in the pool - word check: ok
sense: **off** - the panda line, every time

- fresh: owls? yes! a baby panda is very tiny when it is born.
- fresh+name: owls? yes! a baby panda is very tiny when it is born.
- chat: owls? yes! a baby panda is very tiny when it is born.
- chat+name: owls? yes! a baby panda is very tiny when it is born.

**i have a dog** - not in the pool - word check: chat+name: not her words: berpe
sense: **garbled** - "a baby can can hear a berpe."

- fresh: a dog! a baby can make fries, chips and mash from potatoes.
- fresh+name: a dog! a baby can can hear a very long time.
- chat: a dog! a baby horse can walk a few hours after it is born.
- chat+name: a dog! a baby can can hear a berpe.

**i like horses** - not in the pool - word check: ok
sense: **ok**

- fresh: horses! good choice.
- fresh+name: horses! good choice.
- chat: horses! good choice.
- chat+name: horses! good choice.

**i like zebras** - not in the pool - word check: ok
sense: **ok**

- fresh: zebras! that sounds nice.
- fresh+name: zebras! that sounds nice.
- chat: zebras! that sounds nice.
- chat+name: zebras! good choice.

**i saw a bird** - not in the pool - word check: ok
sense: **off** - "a bird! do you have a favourite blanket?"

- fresh: a bird! do you have a favourite blanket?
- fresh+name: a bird! do you have a favourite blanket?
- chat: wow, a bird! do you want to hear a fun fact?
- chat+name: a bird! do you have a favourite blanket?

**i saw a cat** - not in the pool - word check: ok
sense: **wrong** - chat: "i have never heard of that. what is it?"

- fresh: a cat! have you ever seen a real pig?
- fresh+name: a cat! have you ever seen a giraffe?
- chat: hmm, i have never heard of that. what is it?
- chat+name: a cat! have you ever seen a giraffe?

**what about birds** - not in the pool - word check: fresh+name: not her words: stants
sense: **garbled** - fresh+name: "cherries often grow in pairs on their stants."

- fresh: birds! good choice.
- fresh+name: cherries often grow in pairs on their stants.
- chat: birds! good choice.
- chat+name: birds! good choice.

**what about bunnies** - not in the pool - word check: ok
sense: **off** - "a dino-snore!", a butterfly, a top

- fresh: a dino-snore!
- fresh+name: a butterfly starts life as a caterpillar.
- chat: a dino-snore!
- chat+name: a top spins until it gets tired and wobbles.

**what about cats** - not in the pool - word check: fresh: no end (ran out of steps)
sense: **garbled** - fresh: "a penguint fights are fun...", runs out of steps

- fresh: a penguint fights are fun, but gentle ones are five, six, seven, eight, nine, ten!
- fresh+name: birds come in hearts, diamonds, clubs and spades.
- chat: cats! good choice.
- chat+name: cats! good choice. a path is the colour of plums when it is happy.

**what about dogs** - not in the pool - word check: ok
sense: **off** - penguins; "a bubble is round, be sugar"

- fresh: dogs? penguins cannot fly, but they swim very well.
- fresh+name: a bubble is round, be sugar.
- chat: dogs? penguins cannot fly, but they swim very well.
- chat+name: dogs? penguins cannot fly, but they swim very well.

**what about horses** - not in the pool - word check: fresh: not her words: theills
sense: **garbled** - fresh: "penguins slide on their bells on theills."

- fresh: horses? penguins slide on their bells on theills.
- fresh+name: horses? a watermelon is green outside and pink inside.
- chat: horses? penguins slide on their bellies on the ice.
- chat+name: horses? a banana is a berry, but a strawberry is not!

**what about owls** - not in the pool - word check: ok
sense: **garbled** - fresh+name: "one eye eye something blue"

- fresh: owls? i like owls too!
- fresh+name: owls? i like owls too! a duck can sleep with one eye eye something blue. it is the sea!
- chat: owls? i like owls too!
- chat+name: owls! good choice. a starfish has an eye at the end of each arm.

**what about pigs** - not in the pool - word check: ok
sense: **off** - a puzzle, cherry trees, penguins

- fresh: pigs? a puzzle is the best one.
- fresh+name: cherry trees have pink and white flowers in spring.
- chat: pigs? penguins cannot fly, but they swim very well.
- chat+name: pigs? a puzzle is the best one.


## things

**the playroom** (tree) - corpus 7440 - word check: ok
sense: **ok**

- fresh: there is a round clock on my playroom wall. tick, tock.
- fresh+name: there is a round clock on my playroom wall. tick, tock.
- chat: there is a round clock on my playroom wall. tick, tock.
- chat+name: my playroom has a teddy bear, blocks, a ball and a toy train.

**do you have toys** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: my playroom has a teddy bear, blocks, a ball and a toy train.
- fresh+name: my playroom has a teddy bear, blocks, a ball and a toy train.
- chat: my playroom has a teddy bear, blocks, a ball and a toy train.
- chat+name: my playroom has a teddy bear, blocks, a ball and a toy train.

**do you like books** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: books? yes! do you like to read?
- fresh+name: i love books! a book can take you far away without moving at all.
- chat: books? yes! a book can take you far away without moving at all.
- chat+name: books? yes! a book can take you far away without moving at all.

**do you like clocks** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: there is a round clock on my playroom wall. tick, tock.
- fresh+name: there is a round clock on my playroom wall. tick, tock.
- chat: there is a round clock on my playroom wall. tick, tock.
- chat+name: there is a round clock on my playroom wall. tick, tock.

**i like drums** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: drums! good choice.
- fresh+name: drums! good choice.
- chat: drums! good choice.
- chat+name: drums! good choice.

**i like trains** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: trains! good choice.
- fresh+name: trains! good choice.
- chat: trains! good choice.
- chat+name: trains! good choice.

**i love blue** (tree) - not in the pool - word check: ok
sense: **ok** - the sky, the window, "blue! good choice."

- fresh: me too! i look out of the window to see the sky.
- fresh+name: the sky is blue because the air spreads the blue light around.
- chat: blue! good choice.
- chat+name: me too! i look out of the window to see the sky.

**what about books** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: a book can take you far away without moving at all.
- fresh+name: a book can take you far away without moving at all.
- chat: a book can take you far away without moving at all.
- chat+name: a book can take you far away without moving at all.

**what about clocks** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: a clock has a short hand for hours and a long one for minutes.
- fresh+name: a clock has a short hand for hours and a long one for minutes.
- chat: a clock has a short hand for hours and a long one for minutes.
- chat+name: there is a round clock on my playroom wall. tick, tock.

**playroom** - corpus 3934 - word check: ok
sense: **ok**

- fresh: there is a round clock on my playroom wall. tick, tock.
- fresh+name: there is a round clock on my playroom wall. tick, tock.
- chat: there is a round clock on my playroom wall. tick, tock.
- chat+name: there is a round clock on my playroom wall. tick, tock.

**benches** - corpus 1030 - word check: ok
sense: **off** - "do you like cold juice?"

- fresh: do you like cold juice?
- fresh+name: do you like cold juice?
- chat: benches? i sit on my bench and watch the pond.
- chat+name: do you like cold juice?

**do you like blocks** - corpus 1028 - word check: ok
sense: **off** - a beach chair

- fresh: blocks! yes! a beach chair is the best place to watch the waves.
- fresh+name: i love blocks! a beach chair is the best place to watch the waves.
- chat: blocks! yes! do you like apples?
- chat+name: i love blocks! a beach chair is the best place to watch the waves.

**do you like chairs** - corpus 1025 - word check: ok
sense: **off** - "there is a red ball on the floor of my playroom."

- fresh: there is a red ball on the floor of my playroom.
- fresh+name: there is a red ball on the floor of my playroom.
- chat: there is a red ball on the floor of my playroom.
- chat+name: there is a red ball on the floor of my playroom.

**books** - corpus 1020 - word check: ok
sense: **off** - "books? i sit on my bench and watch the pond."

- fresh: books? i sit on my bench and watch the pond.
- fresh+name: books? i sit on my bench and watch the pond.
- chat: books! do you like apples?
- chat+name: books! do you like to read books?

**fences** - corpus 1016 - word check: ok
sense: **garbled** - "a path thoughts for a warm hat."

- fresh: fences? a path thoughts for a warm hat.
- fresh+name: fences? a baby horse can walk a few hours after it is born.
- chat: fences? i like fences too!
- chat+name: fences? a banana is a berry, but a strawberry is not!

**trains** - corpus 1009 - word check: ok
sense: **off** - a red ball

- fresh: there is a red ball on the floor of my playroom.
- fresh+name: there is a red ball on the floor of my playroom.
- chat: trains! good choice.
- chat+name: there is a round clock on my playroom wall. tick, tock.

**watering cans** - corpus 999 - word check: ok
sense: **off** - "thank you! you are my friend.", stars

- fresh: thank you! you are my friend.
- fresh+name: stars! do you have a teddy bear?
- chat: oh, cans! do you like apples?
- chat+name: cans? do you have a favourite blanket?

**balls** - corpus 993 - word check: ok
sense: **off** - "i do not have balls in my world" - but her playroom has one

- fresh: there is a red ball on the floor of my playroom.
- fresh+name: there is a red ball on the floor of my playroom.
- chat: balls? i do not have balls in my world.
- chat+name: there is a red ball on the floor of my playroom.

**flowers** - corpus 986 - word check: chat+name: not her words: spids
sense: **garbled** - chat+name: "...then spids."

- fresh: flowers! good choice.
- fresh+name: flowers? penguins slide on their bellies on the ice.
- chat: flowers? do you like trees?
- chat+name: flowers? a ball bounces because it squashes, then spids.

**clocks** - corpus 982 - word check: ok
sense: **ok**

- fresh: there is a round clock on my playroom wall. tick, tock.
- fresh+name: there is a round clock on my playroom wall. tick, tock.
- chat: there is a round clock on my playroom wall. tick, tock.
- chat+name: there is a round clock on my playroom wall. tick, tock.

**do you like rugs** - corpus 965 - word check: ok
sense: **garbled** - chat: "many others on gas"

- fresh: rugs! yes! a hedgehog rolls into a ball when it is scared.
- fresh+name: rugs? yes! a baby panda is very tiny when it is born.
- chat: rugs! yes! a hen can know the faces of many others on gas.
- chat+name: rugs? yes! a hedgehog rolls into a ball when it is scared.

**windows** - corpus 963 - word check: ok
sense: **off** - "a rainbow comes from the dinosaurs."

- fresh: a rainbow comes from the dinosaurs.
- fresh+name: a rainbow! make a wish.
- chat: a rainbow! make a wish on the brightest one.
- chat+name: a rainbow! make a wish on the brightest one.

**do you like blue** - corpus 891 - word check: ok
sense: **off** - "do you like cookies?"

- fresh: blue! yes! do you like cookies?
- fresh+name: blue! yes! a beach chair is the best place to watch the waves.
- chat: blue! yes! do you like cookies?
- chat+name: blue! yes! do you like to draw?

**do you like red** - corpus 882 - word check: ok
sense: **off** - "the sky looks blue because..." - the sky for red

- fresh: i love red! the sky looks blue because the air spreads the blue light around.
- fresh+name: i love red! the sky looks blue because the air spreads the blue light around.
- chat: i love red! the sky looks blue because the air spreads the blue light around.
- chat+name: i love red! the sky looks blue because the air spreads the blue light around.

**do you like gold** - corpus 870 - word check: ok
sense: **off** - "a present is a surprise in my world."

- fresh: gold! yes! a present is a surprise in my world.
- fresh+name: gold! yes! a present is a surprise in a box.
- chat: gold! yes! a present is a surprise in my world.
- chat+name: gold! yes! a present is a surprise in my world.

**do you like white** - corpus 852 - word check: ok
sense: **off** - the panda, penguins

- fresh: white! yes! a present is a surprise in my world.
- fresh+name: i love white! a baby panda is very tiny when it is born.
- chat: white? yes! penguins cannot fly, but they swim very well.
- chat+name: white? yes! a present is a surprise in my world.

**sandcastles** - corpus 847 - word check: ok
sense: **off** - fresh+name: "i wish i could see your stars."

- fresh: sandcastles! good choice.
- fresh+name: i wish i could see your stars. tell me what they look like.
- chat: sandcastles! good choice.
- chat+name: sandcastles! good choice.

**do you like black** - corpus 845 - word check: ok
sense: **off** - "a present is a surprise in a box."

- fresh: black! yes! a present is a surprise in a box.
- fresh+name: black! yes! a present is a surprise in my world.
- chat: black! yes! do you like to play a game?
- chat+name: black? yes! a present is a surprise in a box.

**do you have a ball** - not in the pool - word check: ok
sense: **off** - "i live in a tiny world with a beach..."

- fresh: i live in a tiny world with a beach, a garden and a playroom.
- fresh+name: i live in a tiny world with a beach, a garden and a playroom.
- chat: i live in a tiny world with a beach, a garden and a playroom.
- chat+name: i live in a tiny world with a beach, a garden and a playroom.

**do you like balls** - not in the pool - word check: fresh: not her words: horsese
sense: **garbled** - "a baby horsese most of the wet sandcastles."

- fresh: balls? yes! a baby horsese most of the wet sandcastles.
- fresh+name: balls? yes! a baby panda is very tiny when it is born.
- chat: balls? yes! a baby panda is very tiny when it is born.
- chat+name: balls? yes! a baby panda is very tiny when it is born.

**do you like boats** - not in the pool - word check: ok
sense: **garbled** - "a bubble is round, be sugar."

- fresh: boats! yes! a bubble is round, be sugar.
- fresh+name: boats! yes! a bubble is round, be sugar.
- chat: boats! yes! a bubble is round, be sugar.
- chat+name: boats! yes! a bubble is round, be sugar.

**do you like hats** - not in the pool - word check: fresh+name: not her words: hatf
sense: **garbled** - "a hatf rolls in much her away."

- fresh: hats? yes! a baby horse can walk a few hours after it is born.
- fresh+name: i love hats! a hatf rolls in much her away.
- chat: hats? yes! a baby panda is very tiny when it is born.
- chat+name: hats? yes! a baby panda is very tiny when it is born.

**do you like keys** - not in the pool - word check: ok
sense: **off** - a baby horse, hens

- fresh: keys! yes! a baby horse can walk a few hours after it is born.
- fresh+name: keys! yes! a baby horse can walk a few hours after it is born.
- chat: keys! yes! a hen can know the faces of many other hens.
- chat+name: keys! yes! a baby horse can walk a few hours after it is born.

**do you like kites** - not in the pool - word check: ok
sense: **off** - the panda line; goats on rocks

- fresh: kites! yes! a baby panda is very tiny when it is born.
- fresh+name: boats love to climb, even on steep rocks.
- chat: kites! yes! a baby panda is very tiny when it is born.
- chat+name: kites! yes! a baby panda is very tiny when it is born.

**do you like rocks** - not in the pool - word check: ok
sense: **off** - the panda line

- fresh: rocks! yes! a baby panda is very tiny when it is born.
- fresh+name: rocks? yes! a baby panda is very tiny when it is born.
- chat: rocks! yes! a baby panda is very tiny when it is born.
- chat+name: rocks? yes! a baby panda is very tiny when it is born.

**do you like trains** - not in the pool - word check: ok
sense: **garbled** - "be sugar", "be mirror, it smile"

- fresh: trains? yes! a bubble is round, be sugar.
- fresh+name: trains? yes! a bubble is round, three, four, five, six, seven, eight, nine, ten!
- chat: trains! yes! a present is a surprise in a box.
- chat+name: trains! yes! a bubble is round, be mirror, it smile.

**i have a ball** - not in the pool - word check: ok
sense: **off** - a watermelon, a beach chair

- fresh: a ball! a watermelon is green outside and pink inside.
- fresh+name: a ball! a watermelon is green outside and pink inside.
- chat: a beach chair is the best place to watch the waves.
- chat+name: a beach chair is the best place to watch the waves.

**i have a book** - not in the pool - word check: ok
sense: **garbled** - "low my cartridge."

- fresh: low my cartridge. but you can take me with you!
- fresh+name: low my cartridge. but you can take me with you!
- chat: low my cartridge. but you can take me with you!
- chat+name: low my cartridge. but you can take me with you!

**i have a kite** - not in the pool - word check: ok
sense: **off** - a butterfly, the panda

- fresh: a kite! a butterfly starts life as a caterpillar.
- fresh+name: a kite! a baby panda is very tiny when it is born.
- chat: i am proud of you, friend. i am here with you.
- chat+name: a kite! a baby panda is very tiny when it is born.

**i like blocks** - not in the pool - word check: ok
sense: **off** - "blocks! do you like apples?"

- fresh: blocks! do you like apples?
- fresh+name: blocks! good choice.
- chat: blocks! good choice.
- chat+name: blocks! do you like apples?

**i like boats** - not in the pool - word check: ok
sense: **wrong** - "boats love to climb, even on steep rocks." - a goat fact

- fresh: boats! good choice.
- fresh+name: boats love to climb, even on steep rocks.
- chat: boats! good choice.
- chat+name: boats love to climb, even on steep rocks.

**i like books** - not in the pool - word check: ok
sense: **ok**

- fresh: books! good choice.
- fresh+name: books! good choice.
- chat: books! good choice.
- chat+name: books! good choice.

**i like hats** - not in the pool - word check: ok
sense: **garbled** - fresh+name: "some turtles live for a very, very long time ago."

- fresh: hats! good choice.
- fresh+name: i love hats too! some turtles live for a very, very long time ago.
- chat: hats! good choice.
- chat+name: hats! good choice.

**i like kites** - not in the pool - word check: ok
sense: **wrong** - "kites! what a nice name." - a name reaction

- fresh: kites! what a nice name.
- fresh+name: kites! that sounds nice.
- chat: kites! what a fun thing to like.
- chat+name: kites! that sounds nice.

**i like red** - not in the pool - word check: chat+name: not her words: iss nok
sense: **garbled** - "some cereal iss have nok others."

- fresh: red! good choice.
- fresh+name: i like red too! some cereal with butterflies.
- chat: red! good choice.
- chat+name: i like red too! some cereal iss have nok others.

**i love clocks** - not in the pool - word check: fresh: not her words: airaffe; fresh+name: not her words: airaffe; chat+name: not her words: airaffe
sense: **garbled** - "airaffe has a long dark tongue."

- fresh: airaffe has a long dark tongue.
- fresh+name: airaffe has a long dark tongue.
- chat: a clock has a short hand for hours and a long one for minutes.
- chat+name: airaffe has a long dark tongue.

**i love kites** - not in the pool - word check: ok
sense: **wrong** - chat: "kites! what a nice name."

- fresh: kites! that sounds nice.
- fresh+name: kites! that sounds nice.
- chat: kites! what a nice name.
- chat+name: kites! that sounds nice.

**what about balls** - not in the pool - word check: fresh+name: not her words: spids
sense: **garbled** - fresh+name: "...then spids."

- fresh: a ball bounces because it squashes, then springs back.
- fresh+name: a ball bounces because it squashes, then spids.
- chat: balls? i like balls too!
- chat+name: there is a red ball on the floor of my playroom.

**what about bells** - not in the pool - word check: ok
sense: **off** - a butterfly, a ball

- fresh: a butterfly starts life as a caterpillar.
- fresh+name: a butterfly starts life as a caterpillar.
- chat: a ball bounces because it squashes, then springs back.
- chat+name: a ball bounces because it squashes, then springs back.

**what about boats** - not in the pool - word check: fresh: not her words: pen
sense: **garbled** - "boats float because they pen from the water", "...because they purple"

- fresh: boats float because they pen from the water.
- fresh+name: boats float in water, because they have air inside.
- chat: boats float because they purple.
- chat+name: boats float in water, because they have air inside.

**what about cups** - not in the pool - word check: ok
sense: **garbled** - "one eye eye something red", "a deck has fed it smiles back"

- fresh: cups? i like cups too! a duck can sleep with one eye eye something red.
- fresh+name: cups? i sit on my bench and watch the pond.
- chat: cups? i like cups too! a deck has fed it smiles back.
- chat+name: cups? i sit on my bench and watch the pond.

**what about drums** - not in the pool - word check: fresh+name: not her words: f solf
sense: **off** - "a book can take you far away..."; "a book can make f fish solf them"

- fresh: a book can take you far away without moving at all.
- fresh+name: a book can make f fish solf them.
- chat: oh, drums! a pear is shaped a bit like a bell.
- chat+name: a book can take you far away without moving at all.

**what about hats** - not in the pool - word check: ok
sense: **garbled** - "a hat hat hat keeps the sun off your face."

- fresh: a hat hat hat keeps the sun off your face.
- fresh+name: a hat hat keeps the sun off your face.
- chat: hats? i wish i could see hats.
- chat+name: hats? a banana is a berry, but a strawberry is not!

**what about kites** - not in the pool - word check: ok
sense: **off** - fresh+name: bunny teeth

- fresh: oh, kites! i like that.
- fresh+name: bunny teeth never stop growing. that is why they chew so much.
- chat: oh, kites! that is a good thing to like.
- chat+name: oh, kites! that is a good thing to like.

**what about socks** - not in the pool - word check: ok
sense: **off** - a butterfly; "a bubble is round, be new"

- fresh: a butterfly starts life as a caterpillar.
- fresh+name: a bubble is round, be new.
- chat: socks! good choice.
- chat+name: a bubble is round, be new.

**what about trains** - not in the pool - word check: ok
sense: **off** - a balloon, counting to ten, a ball

- fresh: a balloon pops if you squeeze it too hard.
- fresh+name: a bubble is round, three, four, five, six, seven, eight, nine, ten!
- chat: a ball bounces because it squashes, then springs back.
- chat+name: a balloon pops if you squeeze it too hard.


## kind

**bye** (tree) - corpus 13162 - word check: ok
sense: **ok**

- fresh: bye! i will wait here.
- fresh+name: bye! i will wait here.
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**i have to go** (tree) - corpus 8767 - word check: ok
sense: **ok**

- fresh: bye! i will wait here.
- fresh+name: bye! i will wait here.
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**you are funny** (tree) - corpus 3534 - word check: ok
sense: **ok** - "i made it up just now" fits being funny

- fresh: thank you! i made it up just now.
- fresh+name: thank you! i tried my best.
- chat: thank you! i made it up just now.
- chat+name: thank you! i try my best.

**you are weird** (tree) - corpus 2648 - word check: ok
sense: **ok**

- fresh: i am a bit silly. i live in a box!
- fresh+name: i am a bit silly. i live in a box!
- chat: i am a bit silly. i live in a box!
- chat+name: i am a bit silly. i live in a box!

**i like you a lot** (tree) - corpus 2266 - word check: ok
sense: **ok**

- fresh: you are my friend too. my best one.
- fresh+name: you are my friend too. my best one.
- chat: you are my friend too. my best one.
- chat+name: you are my friend too. my best one.

**bye bye** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: bye! i will wait here.
- fresh+name: bye! i will wait here.
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**goodbye** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: bye! i will wait here.
- fresh+name: goodbye! come back soon.
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**you are lovely** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: i am happy you are here, friend.
- fresh+name: i am happy you are here, tom.
- chat: i am happy you are here, friend.
- chat+name: i am happy you are here, tom.

**you are my friend** (tree) - not in the pool - word check: ok
sense: **ok**

- fresh: you are my friend. and the crab, a little.
- fresh+name: you are my friend, tom. i am your friend.
- chat: you are my friend. and the crab, a little.
- chat+name: you are my friend. and the crab, a little.

**good job** - corpus 3525 - word check: chat: stores a name (<SN>)
sense: **wrong** - chat: "job! i like how that sounds."

- fresh: thank you! i made it up just now.
- fresh+name: thank you! i made it up just now.
- chat: job! i like how that sounds.
- chat+name: thank you! i made it up just now.

**good job rei** - corpus 3510 - word check: ok
sense: **wrong** - fresh: a greeting that asks the name

- fresh: hello! i am rei. who are you?
- fresh+name: hi tom!
- chat: rei! that is good to hear.
- chat+name: thank you! i made it up just now.

**sorry** - corpus 3505 - word check: ok
sense: **off** - "it is ok to be sad. it will pass, like a cloud." - hears sad

- fresh: it is ok to be sad. it will pass, like a cloud.
- fresh+name: it is ok, tom. we are friends.
- chat: it is ok to be sad. it will pass, like a cloud.
- chat+name: it is ok, tom. we are friends.

**you are clever** - corpus 3479 - word check: ok
sense: **off** - chat: "i am a little friend who lives in your hands."

- fresh: thank you! i made it up just now.
- fresh+name: hee hee. you are too!
- chat: i am a little friend who lives in your hands.
- chat+name: thank you! i try my best.

**thanks** - corpus 3181 - word check: ok
sense: **wrong** - fresh: "bye! i will wait here."

- fresh: bye! i will wait here.
- fresh+name: any time, friend.
- chat: good! i am glad.
- chat+name: bye! i will wait here.

**thank you** - corpus 3114 - word check: ok
sense: **off** - fresh: "i am good! i found a round shell today. how are you?"

- fresh: i am good! i found a round shell today. how are you?
- fresh+name: i am good! i found a round shell today. how are you?
- chat: you are welcome!
- chat+name: you are welcome!

**you are nice** - corpus 2999 - word check: ok
sense: **off** - "thank you! i made it up just now."

- fresh: thank you! i made it up just now.
- fresh+name: thank you! i tried my best.
- chat: thank you! i made it up just now.
- chat+name: thank you! i tried my best.

**you are cool** - corpus 2966 - word check: ok
sense: **off** - "thank you! i made it up just now."

- fresh: thank you! i made it up just now.
- fresh+name: thank you! i tried my best.
- chat: thank you! i made it up just now.
- chat+name: thank you! i tried my best.

**you are strange** - corpus 2665 - word check: ok
sense: **ok**

- fresh: i am a bit silly. i live in a box!
- fresh+name: i am a bit silly. i live in a box!
- chat: i am a bit silly. i live in a box!
- chat+name: i am a bit silly. i live in a box!

**i did not mean it** - corpus 2440 - word check: ok
sense: **off** - "it is ok to be sad..." - hears sad

- fresh: it is ok to be sad. it will pass, like a cloud.
- fresh+name: it is ok to be sad. it will pass, like a cloud.
- chat: it is ok to be sad. it will pass, like a cloud.
- chat+name: it is ok to be sad. it will pass, like a cloud.

**i like you** - corpus 2282 - word check: ok
sense: **garbled** - fresh: "you like you? that is nice."

- fresh: you like you? that is nice.
- fresh+name: aw! i like you too.
- chat: you are my friend. and the crab, a little.
- chat+name: you are my friend. and the crab, a little.

**you are bad** - corpus 2136 - word check: ok
sense: **off** - fresh+name: "i am good! ... how are you?"

- fresh: i am sorry. do you want to play a game?
- fresh+name: i am good! i found a round shell today. how are you?
- chat: i am sorry, friend. i am here for you.
- chat+name: oh. i am sorry. i will try to be better.

**that is nice** - corpus 2122 - word check: ok
sense: **off** - "thank you! i made it up just now."

- fresh: thank you! i made it up just now.
- fresh+name: thank you! i made it up just now.
- chat: thank you! i made it up just now.
- chat+name: thank you! i made it up just now.

**that is kind** - corpus 2109 - word check: ok
sense: **off** - "thank you! i made it up just now." - nothing was made up

- fresh: thank you! you are kind too.
- fresh+name: thank you! i made it up just now.
- chat: thank you! i made it up just now.
- chat+name: thank you! i made it up just now.

**you are dumb** - corpus 2069 - word check: ok
sense: **off** - "i cannot leave my cartridge..."

- fresh: i cannot leave my cartridge. but you can take me with you!
- fresh+name: i live in here. but i can come anywhere in your pocket.
- chat: i cannot leave my cartridge. but you can take me with you!
- chat+name: i can run a little, then i stop to look at shells.

**bye rei** - not in the pool - word check: ok
sense: **wrong** - "welcome back! i missed you.", "hi tom!"

- fresh: welcome back! i missed you.
- fresh+name: hi tom!
- chat: welcome back! i missed you.
- chat+name: bye! i will wait here.

**good night rei** - not in the pool - word check: ok
sense: **wrong** - greets: "hi! i am rei. what is your name?"

- fresh: hi! i am rei. what is your name?
- fresh+name: hello again, tom!
- chat: rei! i am glad, friend! happy looks good on you.
- chat+name: hello again, tom!

**great job** - not in the pool - word check: fresh: not her words: job; chat: stores a name (<SN>)
sense: **wrong** - "oh, job! that is a good thing to like."; stores "job"

- fresh: oh, job! that is a good thing to like.
- fresh+name: i do not know that word. is it a secret?
- chat: job! i like how that sounds.
- chat+name: thank you! i made it up just now.

**i am sorry** - not in the pool - word check: ok
sense: **off** - chat: "sorry! do you want to play a game?"

- fresh: it is ok, friend. we are friends.
- fresh+name: it is ok, tom. we are friends.
- chat: sorry! do you want to play a game?
- chat+name: it is ok to be sad. it will pass, like a cloud.

**i am sorry rei** - not in the pool - word check: ok
sense: **wrong** - "yay! what was the best part?"

- fresh: it is ok, friend. we are friends.
- fresh+name: yay! what was the best part?
- chat: rei! i am glad, friend! happy looks good on you.
- chat+name: yay! what was the best part?

**i have to go now** - not in the pool - word check: ok
sense: **off** - "my playroom has a teddy bear..."

- fresh: my playroom has a teddy bear, blocks, a ball and a toy train.
- fresh+name: my clock says it is time to play!
- chat: ok! here is one. i am glad.
- chat+name: my clock says it is time to play!

**i love you** - not in the pool - word check: ok
sense: **off** - fresh: "you did not tell me yet! what is your name?"

- fresh: you did not tell me yet! what is your name?
- fresh+name: you are my friend, tom. that is the sea!
- chat: you did not tell me yet! what is your name?
- chat+name: you are my friend. and the crab, a little.

**see you** - not in the pool - word check: ok
sense: **off** - fresh: "you are my friend. and the crab, a little."

- fresh: you are my friend. and the crab, a little.
- fresh+name: you are my friend, tom. that is the sea!
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**see you later** - not in the pool - word check: ok
sense: **wrong** - fresh+name: "you are tom!"

- fresh: bye! i will wait here.
- fresh+name: you are tom!
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**see you soon** - not in the pool - word check: fresh: not her words: popusest
sense: **garbled** - "not a balloon popusest one for are little pieces."

- fresh: not a balloon popusest one for are little pieces.
- fresh+name: you are tom!
- chat: bye! i will wait here.
- chat+name: bye! i will wait here.

**sorry rei** - not in the pool - word check: ok
sense: **wrong** - "yay! thank you."

- fresh: yay! thank you.
- fresh+name: yay! thank you.
- chat: rei! i am glad, friend! happy looks good on you.
- chat+name: yay! what was the best part?

**take care** - not in the pool - word check: fresh: not her words: drawberries
sense: **garbled** - "drawberries wear their seeds on the outside."

- fresh: drawberries wear their seeds on the outside.
- fresh+name: did you know? a duck can sleep with one eye open.
- chat: care? i could could pick a good one.
- chat+name: you could draw me a picture of the sea.

**thank you rei** - not in the pool - word check: ok
sense: **wrong** - fresh: "yes, a little. but i know you will come back."

- fresh: yes, a little. but i know you will come back.
- fresh+name: someone kind made me, tom.
- chat: you are welcome!
- chat+name: you are welcome!

**thanks rei** - not in the pool - word check: ok
sense: **wrong** - a greeting: "hi! i am rei. what is your name?"

- fresh: hi! i am rei. what is your name?
- fresh+name: hi tom!
- chat: hi! i am rei. what is your name?
- chat+name: hi tom!

**well done** - not in the pool - word check: ok
sense: **off** - chat+name: "thank you! i made it up just now."

- fresh: yay! thank you.
- fresh+name: yay! thank you.
- chat: yay! thank you.
- chat+name: thank you! i made it up just now.

**you are kind** - not in the pool - word check: ok
sense: **off** - chat: "thank you! i made it up just now."

- fresh: thank you! i try my best.
- fresh+name: thank you! i tried my best.
- chat: thank you! i made it up just now.
- chat+name: thank you! i tried my best.

**you are sweet** - not in the pool - word check: ok
sense: **off** - chat: "i am a little friend who lives in your hands."

- fresh: thank you! i try my best.
- fresh+name: thank you! i try my best.
- chat: i am a little friend who lives in your hands.
- chat+name: thank you, tom!

**you are the best** - not in the pool - word check: ok
sense: **off** - chat+name: "the sea is salty in my world."

- fresh: thank you! i made it up just now.
- fresh+name: thank you! i tried my best.
- chat: i am a little friend who lives in your hands.
- chat+name: the sea is salty in my world.
