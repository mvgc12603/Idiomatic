from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any


LANGUAGE_ALIASES = {
    "en": "english",
    "eng": "english",
    "english": "english",
    "es": "spanish",
    "esp": "spanish",
    "espanol": "spanish",
    "spanish": "spanish",
    "fr": "french",
    "fra": "french",
    "fre": "french",
    "french": "french",
    "francais": "french"
}

LANGUAGE_MARKERS = {
    "english": {
        "i", "you", "we", "they", "would", "will", "but", "and", "the", "that", "this",
        "with", "without", "because", "when", "for", "not", "like", "dont", "doesnt",
        "my", "your", "is", "are", "was", "were", "want", "feel", "felt", "say",
        "said", "think", "thought", "mean", "means"
    },
    "spanish": {
        "yo", "tu", "usted", "nosotros", "pero", "y", "el", "la", "los", "las", "que",
        "eso", "esto", "con", "sin", "porque", "cuando", "para", "no", "me", "gusta",
        "estaba", "manteniendo", "es", "son", "mi", "mis", "un", "una", "lo", "por",
        "quiero", "siento", "sentia", "digo", "dije", "decir", "significa"
    },
    "french": {
        "je", "tu", "vous", "nous", "mais", "et", "le", "la", "les", "que", "avec",
        "sans", "parce", "quand", "pour", "pas", "ne", "des", "gouts", "couleurs",
        "ce", "cest", "mon", "mes", "un", "une", "du", "veux", "dire", "sens"
    }
}

STOPWORDS = {
    "a", "an", "and", "are", "as", "be", "by", "for", "from", "in", "is", "it", "of",
    "on", "or", "someone", "something", "that", "the", "their", "to", "very", "when",
    "with", "without", "you", "your",
    "al", "algo", "con", "de", "del", "el", "en", "es", "la", "las", "lo", "los",
    "muy", "o", "para", "por", "que", "se", "ser", "su", "un", "una",
    "ce", "cest", "dans", "des", "du", "et", "etre", "le", "les", "ne", "pas",
    "pour", "qui", "sur", "une"
}


IDIOM_DATABASE: list[dict[str, Any]] = [
    {
        "meaning": "personal taste is subjective",
        "forms": {
            "spanish": ["sobre gustos no hay nada escrito", "para gustos los colores", "en gustos se rompen generos"],
            "english": ["there is no accounting for taste", "to each their own", "different strokes for different folks"],
            "french": ["les gouts et les couleurs ne se discutent pas", "des gouts et des couleurs on ne discute pas"]
        }
    },
    {
        "meaning": "it is raining very heavily",
        "forms": {
            "spanish": ["llover a cantaros", "caer un aguacero"],
            "english": ["raining cats and dogs", "pouring rain", "raining buckets"],
            "french": ["pleuvoir des cordes", "il pleut des cordes"]
        }
    },

    {
        "meaning": "better to have one thing than hope for many",
        "forms": {
            "spanish": ["mas vale pajaro en mano que cien volando"],
            "english": ["a bird in the hand is worth two in the bush"],
            "french": ["un tien vaut mieux que deux tu l'auras"]
             }
             },
    {
        "meaning": "the final problem that makes patience run out",
        "forms": {
            "spanish": ["la gota que colmo el vaso", "la gota que derramo el vaso", 'la ultima gota'],
            "english": ["the last straw", "the final straw", 'the straw that broke the camels back'],
            "french": ["la goutte d eau qui fait deborder le vase"]
        }
    },
    {
        "meaning": "something is very easy",
        "forms": {
            "spanish": ["ser pan comido"],
            "english": ["piece of cake", "easy as pie"],
            "french": ["c est du gateau", "simple comme bonjour"]
        }
    },
    {
        "meaning": "to reveal a secret",
        "forms": {
            "spanish": ["soltar la sopa", "irse de la lengua"],
            "english": ["spill the beans", "let the cat out of the bag"],
            "french": ["vendre la meche"]
        }
    },
    {
        "meaning": "to die in an informal or comic way",
        "forms": {
            "spanish": ["estirar la pata", "colgar los tenis"],
            "english": ["kick the bucket"],
            "french": ["casser sa pipe"]
        }
    },
    {
        "meaning": "to be very expensive",
        "forms": {
            "spanish": ["costar un ojo de la cara"],
            "english": ["cost an arm and a leg", "costs an arm and a leg"],
            "french": ["couter les yeux de la tete"]
        }
    },
    {
        "meaning": "to work or study late into the night",
        "forms": {
            "spanish": ["quemarse las pestanas", "trabajar hasta tarde"],
            "english": ["burn the midnight oil", "burning the midnight oil"],
            "french": ["travailler d arrache-pied"]
        }
    },
    {
        "meaning": "something happens very rarely",
        "forms": {
            "spanish": ["de higos a brevas", "cada muerte de obispo"],
            "english": ["once in a blue moon"],
            "french": ["tous les trente-six du mois"]
        }
    },
    {
        "meaning": "to be joking or teasing",
        "forms": {
            "spanish": ["tomar el pelo", "me estas tomando el pelo"],
            "english": ["pull someone's leg", "pulling my leg"],
            "french": ["faire marcher quelqu un"]
        }
    },
    {
        "meaning": "to avoid saying something directly",
        "forms": {
            "spanish": ["andarse por las ramas"],
            "english": ["beat around the bush"],
            "french": ["tourner autour du pot"]
        }
    },
    {
        "meaning": "to make a bad situation worse",
        "forms": {
            "spanish": ["echar lena al fuego"],
            "english": ["add fuel to the fire"],
            "french": ["jeter de l huile sur le feu"]
        }
    },
    {
        "meaning": "to be in a risky or precarious situation",
        "forms": {
            "spanish": ["estar en la cuerda floja"],
            "english": ["be on thin ice", "on thin ice"],
            "french": ["etre sur la corde raide"]
        }
    },
    {
        "meaning": "to be forced to choose between two bad options",
        "forms": {
            "spanish": ["estar entre la espada y la pared", "verse entre la espada y la pared"],
            "english": ["be between a rock and a hard place"],
            "french": ["etre entre le marteau et l enclume"]
        }
    },
    {
        "meaning": "now it is your responsibility to act",
        "forms": {
            "spanish": ["la pelota esta en tu cancha", "esta en tus manos"],
            "english": ["the ball is in your court"],
            "french": ["la balle est dans ton camp"]
        }
    },
    {
        "meaning": "to accept a difficult situation",
        "forms": {
            "spanish": ["hacer de tripas corazon"],
            "english": ["bite the bullet", "eat the frog"],
            "french": ["prendre son courage a deux mains"]
        }
    },
    {
        "meaning": "to go to sleep",
        "forms": {
            "spanish": ["irse a dormir", "irse al sobre"],
            "english": ["hit the sack", "hit the hay"],
            "french": ["aller au lit"]
        }
    },
    {
        "meaning": "to feel sick",
        "forms": {
            "spanish": ["sentirse mal", "estar pachucho"],
            "english": ["under the weather"],
            "french": ["ne pas etre dans son assiette"]
        }
    },
    {
        "meaning": "to begin an interaction and reduce awkwardness",
        "forms": {
            "spanish": ["romper el hielo"],
            "english": ["break the ice"],
            "french": ["briser la glace"]
        }
    },
    {
        "meaning": "to describe exactly what is true",
        "forms": {
            "spanish": ["dar en el clavo"],
            "english": ["hit the nail on the head"],
            "french": ["mettre le doigt dessus"]
        }
    },

    {
        "meaning": "to do something cheaply or badly by skipping proper steps",
        "forms": {
            "spanish": ["tomar atajos", "hacer algo a medias"],
            "english": ["cut corners"],
            "french": ["faire des economies de bouts de chandelle"]
        }
    },
    {
        "meaning": "to stop working for now",
        "forms": {
            "spanish": ["dar por terminado", "dejarlo por hoy"],
            "english": ["call it a day"],
            "french": ["en rester la pour aujourd hui"]
        }
    },
    {
        "meaning": "to become too nervous to proceed",
        "forms": {
            "spanish": ["echarse atras", "acobardarse"],
            "english": ["get cold feet"],
            "french": ["avoir la frousse"]
        }
    },
    {
        "meaning": "to miss an opportunity",
        "forms": {
            "spanish": ["perder el tren", "perder la oportunidad"],
            "english": ["miss the boat"],
            "french": ["rater le coche"]
        }
    },
    {
        "meaning": "something will never happen",
        "forms": {
            "spanish": ["cuando las ranas crien pelo", "cuando los cerdos vuelen"],
            "english": ["when pigs fly"],
            "french": ["quand les poules auront des dents"]
        }
    },
    {
        "meaning": "to be very hungry",
        "forms": {
            "spanish": ["tener un hambre de lobo"],
            "english": ["be starving", "hungry as a wolf"],
            "french": ["avoir une faim de loup"]
        }
    },
    {
        "meaning": "to be extremely busy",
        "forms": {
            "spanish": ["estar hasta arriba", "estar hasta el cuello"],
            "english": ["have a lot on one's plate", "be swamped"],
            "french": ["avoir du pain sur la planche"]
        }
    },
    {
        "meaning": "to make a great effort",
        "forms": {
            "spanish": ["hacer todo lo posible"],
            "english": ["go the extra mile"],
            "french": ["se mettre en quatre"]
        }
    },
    {
        "meaning": "to not understand anything",
        "forms": {
            "spanish": ["no entender ni jota"],
            "english": ["not understand a word"],
            "french": ["ne rien comprendre"]
        }
    },
    {
        "meaning": "to be very lucky",
        "forms": {
            "spanish": ["tener mucha suerte", "nacer de pie"],
            "english": ["strike it lucky"],
            "french": ["avoir de la chance"]
        }
    },
    {
        "meaning": "to be careful",
        "forms": {
            "spanish": ["andar con pies de plomo"],
            "english": ["tread carefully"],
            "french": ["marcher sur des oeufs"]
        }
    },
    {
        "meaning": "to be very calm",
        "forms": {
            "spanish": ["mantener la calma"],
            "english": ["keep one's cool"],
            "french": ["garder son sang-froid"]
        }
    },
    {
        "meaning": "to take advantage of someone",
        "forms": {
            "spanish": ["tomar el pelo", "aprovecharse de alguien"],
            "english": ["take someone for a ride"],
            "french": ["mener quelqu un en bateau"]
        }
    },
    {
        "meaning": "people with similar traits spend time together",
        "forms": {
            "spanish": ["dios los cria y ellos se juntan", "los pajaros se conoce por la tonada", "dime con quién andas y te diré quién eres"],
            "english": ["birds of a feather flock together"],
            "french": ["qui se ressemble se assemble"]
        }
    },
    {
        "meaning": "better late than never",
        "forms": {
            "spanish": ["mas vale tarde que nunca"],
            "english": ["better late than never"],
            "french": ["mieux vaut tard que jamais"]
        }
    },
    {
        "meaning": "people take advantage of confusing or chaotic situations in order to benefit",
        "forms": {
            "spanish": ["rio revuelto ganancia de pescadores"],
            "english": ["troubled waters, fisherman's gain, it's good fishing in troubled waters"],
            "french": ["les eaux troubles sont une aubaine pour le pêcheur"]
        }
    },
    {
        "meaning": "appearances can be deceiving",
        "forms": {
            "spanish": ["las apariencias enganan"],
            "english": ["appearances can be deceiving"],
            "french": ["les apparences sont trompeuses"]
        }
    },
    {
        "meaning": "actions matter more than words",
        "forms": {
            "spanish": ["obras son amores y no buenas razones"],
            "english": ["actions speak louder than words"],
            "french": ["les actes valent mieux que les paroles"]
        }
    },
    {
        "meaning": "do not judge by appearance",
        "forms": {
            "spanish": ["no juzgues un libro por su portada"],
            "english": ["do not judge a book by its cover"],
            "french": ["il ne faut pas juger sur les apparences"]
        }
    },
    {
        "meaning": "every cloud has a silver lining",
        "forms": {
            "spanish": ["no hay mal que por bien no venga"],
            "english": ["every cloud has a silver lining"],
            "french": ["a quelque chose malheur est bon"]
        }
    },
    {
        "meaning": "do not count on something before it happens",
        "forms": {
            "spanish": ["no vendas la piel del oso antes de cazarlo"],
            "english": ["do not count your chickens before they hatch"],
            "french": ["il ne faut pas vendre la peau de l ours avant de l avoir tue"]
        }
    },
    {
        "meaning": "better to prevent a problem than fix it",
        "forms": {
            "spanish": ["mas vale prevenir que curar"],
            "english": ["an ounce of prevention is worth a pound of cure"],
            "french": ["mieux vaut prevenir que guerir"]
        }
    },
    {
        "meaning": "the early person gets the opportunity",
        "forms": {
            "spanish": ["a quien madruga dios le ayuda"],
            "english": ["the early bird catches the worm"],
            "french": ["l avenir appartient a ceux qui se levent tot"]
        }
    },
    {
        "meaning": "there is no gain without effort",
        "forms": {
            "spanish": ["quien algo quiere algo le cuesta"],
            "english": ["no pain no gain"],
            "french": ["on n a rien sans rien"]
        }
    },
    {
        "meaning": "silence can mean agreement",
        "forms": {
            "spanish": ["quien calla otorga"],
            "english": ["silence gives consent"],
            "french": ["qui ne dit mot consent"]
        }
    },
    {
        "meaning": "do not look for problems where there are none",
        "forms": {
            "spanish": ["buscarle tres patas al gato"],
            "english": ["split hairs", "look for problems where there are none"],
            "french": ["chercher midi a quatorze heures"]
        }
    },
    {
        "meaning": "speak frankly and clearly",
        "forms": {
            "spanish": ["hablar claro"],
            "english": ["call a spade a spade"],
            "french": ["appeler un chat un chat"]
        }
    },
    {
        "meaning": "to join a popular trend",
        "forms": {
            "spanish": ["subirse al carro"],
            "english": ["jump on the bandwagon"],
            "french": ["prendre le train en marche"]
        }
    },
    {
        "meaning": "this drink or meal is my treat",
        "forms": {
            "spanish": ["esta ronda la pago yo", "te invito"],
            "english": ["this round is on me", "my treat"],
            "french": ["c est ma tournee"]
        }
    },
    {
        "meaning": "sometimes you win and sometimes you lose",
        "forms": {
            "spanish": ["unas veces se gana otras se pierde"],
            "english": ["you win some you lose some"],
            "french": ["on ne peut pas gagner a tous les coups"]
        }
    },
    {
        "meaning": "to stop trying or admit defeat",
        "forms": {
            "spanish": ["tirar la toalla"],
            "english": ["throw in the towel"],
            "french": ["jeter l eponge"]
        }
    },
    {
        "meaning": "to refuse to hear what someone says",
        "forms": {
            "spanish": ["no hay peor sordo que el que no quiere oir"],
            "english": ["none so deaf as those who will not hear"],
            "french": ["il n est pire sourd que celui qui ne veut pas entendre"]
        }
    },
    {
        "meaning": "a new opportunity follows a setback",
        "forms": {
            "spanish": ["cuando se cierra una puerta se abre una ventana"],
            "english": ["when one door closes another opens"],
            "french": ["quand une porte se ferme une autre s ouvre"]
        }
    },
    {
        "meaning": "people get the result they deserve",
        "forms": {
            "spanish": ["cada uno tiene lo que se merece"],
            "english": ["people get what they deserve"],
            "french": ["on recolte ce que l on seme"]
        }
    },
    {
        "meaning": "curiosity can get you into trouble",
        "forms": {
            "spanish": ["la curiosidad mato al gato"],
            "english": ["curiosity killed the cat"],
            "french": ["la curiosite est un vilain defaut"]
        }
    },
    {
        "meaning": "to have useful connections or influence",
        "forms": {
            "spanish": ["tener enchufe"],
            "english": ["be well connected", "have friends in high places"],
            "french": ["avoir le bras long"]
        }
    },
    {
        "meaning": "do not harm someone who supports you",
        "forms": {
            "spanish": ["no muerdas la mano que te da de comer"],
            "english": ["do not bite the hand that feeds you"],
            "french": ["ne mords pas la main qui te nourrit"]
        }
    },
    {
        "meaning": "experts may neglect their own household",
        "forms": {
            "spanish": ["en casa del herrero cuchillo de palo"],
            "english": ["the shoemaker's children go barefoot"],
            "french": ["les cordonniers sont toujours les plus mal chausses"]
        }
    },
    {
        "meaning": "familiar problems are safer than unknown risks",
        "forms": {
            "spanish": ["mas vale lo malo conocido que lo bueno por conocer"],
            "english": ["better the devil you know"],
            "french": ["mieux vaut un mal connu qu un bien qui reste a connaitre"]
        }
    },
    {
        "meaning": "people misbehave when authority is absent",
        "forms": {
            "spanish": ["cuando el gato no esta los ratones bailan"],
            "english": ["when the cat is away the mice will play"],
            "french": ["quand le chat n est pas la les souris dansent"]
        }
    },
    {
        "meaning": "a person is strange or unusual",
        "forms": {
            "spanish": ["ser un bicho raro"],
            "english": ["be an oddball", "be a weirdo"],
            "french": ["etre un drole d oiseau"]
        }
    },
    {
        "meaning": "a place is very far away",
        "forms": {
            "spanish": ["estar en el quinto pino"],
            "english": ["be in the middle of nowhere"],
            "french": ["etre au bout du monde"]
        }
    },
    {
        "meaning": "to be rich",
        "forms": {
            "spanish": ["estar forrado"],
            "english": ["be loaded"],
            "french": ["etre plein aux as"]
        }
    },
    {
        "meaning": "children resemble their parents",
        "forms": {
            "spanish": ["de tal palo tal astilla"],
            "english": ["the apple does not fall far from the tree", "like father like son"],
            "french": ["tel pere tel fils"]
        }
    },
    {
        "meaning": "to accomplish two goals with one action",
        "forms": {
            "spanish": ["matar dos pajaros de un tiro"],
            "english": ["kill two birds with one stone"],
            "french": ["faire d une pierre deux coups"]
        }
    },
    {
        "meaning": "not seeing something makes it less painful",
        "forms": {
            "spanish": ["ojos que no ven corazon que no siente"],
            "english": ["out of sight out of mind"],
            "french": ["loin des yeux loin du coeur"]
        }
    },
    {
        "meaning": "valuable things are not always flashy",
        "forms": {
            "spanish": ["no es oro todo lo que reluce"],
            "english": ["all that glitters is not gold"],
            "french": ["tout ce qui brille n est pas or"]
        }
    },
    {
        "meaning": "a person is unimportant",
        "forms": {
            "spanish": ["ser un don nadie", "ser un cero a la izquierda"],
            "english": ["be a nobody", "be worthless"],
            "french": ["etre un moins que rien"]
        }
    },
    {
        "meaning": "shared trouble is easier to bear",
        "forms": {
            "spanish": ["las penas compartidas saben a menos"],
            "english": ["a trouble shared is a trouble halved"],
            "french": ["peine partagee est a moitie soulagee"]
        }
    },
    {
        "meaning": "to reveal one's sexual orientation publicly",
        "forms": {
            "spanish": ["salir del armario"],
            "english": ["come out of the closet"],
            "french": ["sortir du placard"]
        }
    },
    {
        "meaning": "to be very happy",
        "forms": {
            "spanish": ["estar como unas castanuelas"],
            "english": ["be happy as a clam", "be on cloud nine"],
            "french": ["etre aux anges"]
        }
    },
    {
        "meaning": "variety makes life enjoyable",
        "forms": {
            "spanish": ["en la variedad esta el gusto"],
            "english": ["variety is the spice of life"],
            "french": ["il faut de tout pour faire un monde"]
        }
    },
    {
        "meaning": "an important or powerful person",
        "forms": {
            "spanish": ["ser un pez gordo"],
            "english": ["be a big fish", "be a big shot"],
            "french": ["etre une grosse legume"]
        }
    },
    {
        "meaning": "cleverness matters more than strength",
        "forms": {
            "spanish": ["mas vale mana que fuerza"],
            "english": ["brain over brawn"],
            "french": ["mieux vaut ruse que force"]
        }
    },
    {
        "meaning": "mutual help or favors",
        "forms": {
            "spanish": ["hoy por ti manana por mi"],
            "english": ["you scratch my back and i will scratch yours"],
            "french": ["un service en vaut un autre"]
        }
    },
    {
        "meaning": "risk is needed to gain something",
        "forms": {
            "spanish": ["quien no arriesga no gana"],
            "english": ["nothing ventured nothing gained"],
            "french": ["qui ne risque rien n a rien"]
        }
    },
    {
        "meaning": "people who threaten loudly rarely act",
        "forms": {
            "spanish": ["perro ladrador poco mordedor"],
            "english": ["barking dogs seldom bite"],
            "french": ["chien qui aboie ne mord pas"]
        }
    },
    {
        "meaning": "to act silly or clown around",
        "forms": {
            "spanish": ["hacer el mono"],
            "english": ["clown around", "act the fool"],
            "french": ["faire le clown"]
        }
    },
    {
        "meaning": "all methods can lead to the same result",
        "forms": {
            "spanish": ["todos los caminos llevan a roma"],
            "english": ["all roads lead to Rome"],
            "french": ["tous les chemins menent a Rome"]
        }
    },
    {
        "meaning": "to have a bad temper",
        "forms": {
            "spanish": ["tener mala leche", "estar de mala uva"],
            "english": ["have a bad temper", "be a bad apple"],
            "french": ["avoir mauvais caractere"]
        }
    },

    {
        "meaning": "to be wary, learn from experience",
        "forms": {
            "spanish": ["el que se quemo con leche cuando ve una vaca llora"],
            "english": ["once bitten, twice shy"],
            "french": ["chat échaudé craint l'eau froide"],
            "turkish": ["sütten ağzı yanan yoğurdu üfleyerek yer"]
        }
    },

    {
        "meaning": "romantic partner or ideal match",
        "forms": {
            "spanish": ["ser la media naranja"],
            "english": ["be the better half", "be one's other half"],
            "french": ["etre l ame soeur"]
        }
    },
    {
        "meaning": "to make a mistake",
        "forms": {
            "spanish": ["meter la pata"],
            "english": ["put one's foot in it", "screw up"],
            "french": ["mettre les pieds dans le plat"]
        }
    },
    {
        "meaning": "to change sides for personal advantage",
        "forms": {
            "spanish": ["ser un chaquetero"],
            "english": ["be a turncoat", "be a flip-flopper"],
            "french": ["retourner sa veste"]
        }
    },
    {
        "meaning": "a hint is enough for a smart person",
        "forms": {
            "spanish": ["a buen entendedor pocas palabras bastan"],
            "english": ["a word to the wise is enough"],
            "french": ["a bon entendeur salut"]
        }
    },
    {
        "meaning": "to lose an opportunity by being absent or slow",
        "forms": {
            "spanish": ["quien fue a Sevilla perdio su silla", "camaron que se duerme se lo lleva la corriente"],
            "english": ["you snooze you lose"],
            "french": ["qui va a la chasse perd sa place"]
        }
    },
    {       "meaning": "to lose an opportunity by being absent or slow",
            "forms": {
                "spanish": ["todos los caminos llevan a roma"],
                "english": ["all paths lead to rome"],
                "french": ["qui va a la chasse perd sa place"]
            }
            },
    {
        "meaning": "to be drunk",
        "forms": {
            "spanish": ["pillarse un pedo", "estar borracho"],
            "english": ["get drunk", "be wasted"],
            "french": ["etre bourre"]
        }
    },
    {
        "meaning": "to be crazy or eccentric",
        "forms": {
            "spanish": ["loco como una cabra"],
            "english": ["be crazy", "be off one's rocker"],
            "french": ["avoir une araignee au plafond"]
        }
    },
    {
        "meaning": "just in case",
        "forms": {
            "spanish": ["por si las moscas"],
            "english": ["just in case"],
            "french": ["au cas ou"]
        }
    },
    {
        "meaning": "to flatter someone for advantage",
        "forms": {
            "spanish": ["hacer la pelota"],
            "english": ["suck up to someone", "brown-nose"],
            "french": ["passer de la pommade"]
        }
    },
    {
        "meaning": "to help with effort",
        "forms": {
            "spanish": ["arrimar el hombro", "echar una mano"],
            "english": ["lend a hand", "pitch in"],
            "french": ["mettre la main a la pate"]
        }
    },
    {
        "meaning": "to be a thief",
        "forms": {
            "spanish": ["ser un chorizo"],
            "english": ["be a thief", "be crooked"],
            "french": ["etre un voleur"]
        }
    },
    {
        "meaning": "to be out of fashion or outdated",
        "forms": {
            "spanish": ["ser del ano de la pera"],
            "english": ["be old-fashioned", "be out of date"],
            "french": ["dater de Mathusalem"]
        }
    },
    {
        "meaning": "to be sacrificed for someone else's purpose",
        "forms": {
            "spanish": ["ser carne de canon"],
            "english": ["be cannon fodder", "be thrown under the bus"],
            "french": ["servir de chair a canon"]
        }
    },
    {
        "meaning": "to be soaked",
        "forms": {
            "spanish": ["estar como una sopa"],
            "english": ["be soaked to the bone"],
            "french": ["etre trempe jusqu aux os"]
        }
    },
    {
        "meaning": "something does not matter",
        "forms": {
            "spanish": ["importar un pimiento", "me importa un comino"],
            "english": ["not give a damn", "not matter"],
            "french": ["s en moquer comme de l an quarante"]
        }
    },
    {
        "meaning": "to focus excessively on minor details",
        "forms": {
            "spanish": ["buscarle tres pies al gato"],
            "english": ["split hairs", "nitpick"],
            "french": ["chercher la petite bete"]
        }
    },
    {
        "meaning": "to give up and ask for the answer",
        "forms": {
            "spanish": ["darse por vencido", "no saber la respuesta"],
            "english": ["give up"],
            "french": ["donner sa langue au chat"]
        }
    },
    {
        "meaning": "to be very strict about something",
        "forms": {
            "spanish": ["ser muy estricto"],
            "english": ["be a stickler for something"],
            "french": ["etre a cheval sur quelque chose"]
        }
    },
    {
        "meaning": "to be pampered and comfortable",
        "forms": {
            "spanish": ["estar como un rey"],
            "english": ["be pampered", "live like royalty"],
            "french": ["etre comme un coq en pate"]
        }
    },
    {
        "meaning": "to wait a long time standing",
        "forms": {
            "spanish": ["esperar de pie mucho tiempo"],
            "english": ["wait around forever"],
            "french": ["faire le pied de grue"]
        }
    },
    {
        "meaning": "it is very cold",
        "forms": {
            "spanish": ["hace un frio que pela"],
            "english": ["it is freezing"],
            "french": ["faire un froid de canard"]
        }
    },
    {
        "meaning": "something suspicious is going on",
        "forms": {
            "spanish": ["hay gato encerrado", "algo huele mal"],
            "english": ["something fishy is going on"],
            "french": ["il y a anguille sous roche"]
        }
    },

    {
        "meaning": "something suspicious is going on",
        "forms": {
            "spanish": ["gato con guantes no atrapa ratones"],
            "english": ["something fishy is going on"],
            "french": ["il y a anguille sous roche"]
        }
    },

    {
        "meaning": "unable to do anything right",
        "forms": {
            "spanish": ["no dar pie con bola"],
            "english": ["unable to do anything right', can't hit the ball"],
            "french": ["	faire tout de travers"]
        }
    },

    {
        "meaning": "to do things in the wrong order",
        "forms": {
            "spanish": ["empezar la casa por el tejado"],
            "english": ["put the cart before the horse"],
            "french": ["mettre la charrue avant les boeufs"]
        }
    },
    {
        "meaning": "to clarify something directly",
        "forms": {
            "spanish": ["poner los puntos sobre las ies"],
            "english": ["dot the i's and cross the t's", "set the record straight"],
            "french": ["mettre les points sur les i"]
        }
    },
    {
        "meaning": "nothing special or remarkable",
        "forms": {
            "spanish": ["no ser nada del otro mundo"],
            "english": ["nothing to write home about"],
            "french": ["ne pas casser trois pattes a un canard"]
        }
    },
    {
        "meaning": "to suddenly change the subject",
        "forms": {
            "spanish": ["cambiar de tema de golpe"],
            "english": ["jump from one topic to another"],
            "french": ["passer du coq a l ane"]
        }
    },
    {
        "meaning": "to stand someone up",
        "forms": {
            "spanish": ["dejar plantado a alguien"],
            "english": ["stand someone up"],
            "french": ["poser un lapin"]
        }
    },
    {
        "meaning": "to get offended suddenly",
        "forms": {
            "spanish": ["ofenderse", "picarse"],
            "english": ["take offense"],
            "french": ["prendre la mouche"]
        }
    },
    {
        "meaning": "to say nonsense or lies",
        "forms": {
            "spanish": ["decir tonterias", "contar mentiras"],
            "english": ["talk nonsense"],
            "french": ["raconter des salades"]
        }
    },
    {
        "meaning": "to feel comfortable and at ease",
        "forms": {
            "spanish": ["sentirse como pez en el agua"],
            "english": ["feel at home", "be in one's element"],
            "french": ["se sentir comme un poisson dans l eau"]
        }
    },
    {
        "meaning": "to coax information out of someone",
        "forms": {
            "spanish": ["sonsacar a alguien"],
            "english": ["worm something out of someone"],
            "french": ["tirer les vers du nez"]
        }
    },
    {
        "meaning": "to meddle in something",
        "forms": {
            "spanish": ["meter baza", "meterse donde no le llaman"],
            "english": ["put in one's two cents", "meddle"],
            "french": ["mettre son grain de sel"]
        }
    },
    {
        "meaning": "to speed up",
        "forms": {
            "spanish": ["pisar el acelerador"],
            "english": ["step on it"],
            "french": ["appuyer sur le champignon"]
        }
    },
    {
        "meaning": "to overestimate what one can handle",
        "forms": {
            "spanish": ["abarcar demasiado"],
            "english": ["bite off more than one can chew"],
            "french": ["avoir les yeux plus gros que le ventre"]
        }
    },
    {
        "meaning": "to fall in love too easily",
        "forms": {
            "spanish": ["enamorarse facilmente"],
            "english": ["fall in love too easily"],
            "french": ["avoir un coeur d artichaut"]
        }
    },
    {
        "meaning": "to criticize someone behind their back",
        "forms": {
            "spanish": ["criticar a espaldas de alguien"],
            "english": ["talk behind someone's back"],
            "french": ["casser du sucre sur le dos de quelqu un"]
        }
    },
    {
        "meaning": "it is none of your business",
        "forms": {
            "spanish": ["no es asunto tuyo"],
            "english": ["none of your business"],
            "french": ["ce ne sont pas tes oignons"]
        }
    },
    {
        "meaning": "all hope is lost",
        "forms": {
            "spanish": ["todo esta perdido"],
            "english": ["it is all over"],
            "french": ["c est la fin des haricots", "les carottes sont cuites"]
        }
    },
    {
        "meaning": "to be unimportant",
        "forms": {
            "spanish": ["no contar para nada"],
            "english": ["not count for much"],
            "french": ["compter pour du beurre"]
        }
    },
    {
        "meaning": "to compromise",
        "forms": {
            "spanish": ["llegar a un punto medio"],
            "english": ["meet halfway"],
            "french": ["couper la poire en deux"]
        }
    },
    {
        "meaning": "to criticize something one benefits from",
        "forms": {
            "spanish": ["criticar lo que te beneficia"],
            "english": ["bite the hand that feeds you"],
            "french": ["cracher dans la soupe"]
        }
    },
    {
        "meaning": "to make a situation more complicated than necessary",
        "forms": {
            "spanish": ["hacer una montana de un grano de arena"],
            "english": ["make a mountain out of a molehill"],
            "french": ["en faire tout un fromage"]
        }
    },
    {
        "meaning": "to be very short",
        "forms": {
            "spanish": ["ser muy bajo"],
            "english": ["be knee-high"],
            "french": ["etre haut comme trois pommes"]
        }
    },
    {
        "meaning": "to be the person who gets fooled",
        "forms": {
            "spanish": ["ser el tonto de la pelicula"],
            "english": ["be the fall guy"],
            "french": ["etre le dindon de la farce"]
        }
    },
    {
        "meaning": "to fail completely",
        "forms": {
            "spanish": ["fracasar"],
            "english": ["draw a blank", "come up empty"],
            "french": ["faire chou blanc"]
        }
    },
    {
        "meaning": "to succeed financially",
        "forms": {
            "spanish": ["hacer su agosto"],
            "english": ["make a killing"],
            "french": ["faire son beurre"]
        }
    },
    {
        "meaning": "the situation is tense",
        "forms": {
            "spanish": ["hay tension"],
            "english": ["there is tension in the air"],
            "french": ["il y a de l eau dans le gaz"]
        }
    },
    {
        "meaning": "to work faster or harder",
        "forms": {
            "spanish": ["redoblar esfuerzos"],
            "english": ["double down", "step up the pace"],
            "french": ["mettre les bouchees doubles"]
        }
    },
    {
        "meaning": "to gain experience",
        "forms": {
            "spanish": ["ganar experiencia"],
            "english": ["gain experience"],
            "french": ["prendre de la bouteille"]
        }
    },
    {
        "meaning": "to produce useful results",
        "forms": {
            "spanish": ["dar frutos"],
            "english": ["bear fruit"],
            "french": ["porter ses fruits"]
        }
    },
    {
        "meaning": "to be cheated",
        "forms": {
            "spanish": ["ser enganado"],
            "english": ["be taken for a ride"],
            "french": ["se faire rouler dans la farine"]
        }
    },
    {
        "meaning": "to faint",
        "forms": {
            "spanish": ["desmayarse"],
            "english": ["pass out", "faint"],
            "french": ["tomber dans les pommes"]
        }
    },
    {
        "meaning": "a controversial issue that is awkward to handle",
        "forms": {
            "spanish": ["tema candente"],
            "english": ["hot potato"],
            "french": ["sujet brulant"]
        }
    },
    {
        "meaning": "fake or insincere sadness",
        "forms": {
            "spanish": ["lagrimas de cocodrilo"],
            "english": ["crocodile tears"],
            "french": ["larmes de crocodile"]
        }
    },
    {
        "meaning": "to stay silent",
        "forms": {
            "spanish": ["cerrar el pico"],
            "english": ["zip your lip"],
            "french": ["tenir sa langue"]
        }
    },
    {
        "meaning": "a backup plan",
        "forms": {
            "spanish": ["plan b"],
            "english": ["plan B"],
            "french": ["plan B"]
        }
    },
    {
        "meaning": "to keep something secret",
        "forms": {
            "spanish": ["guardar el secreto"],
            "english": ["keep it under your hat"],
            "french": ["garder ca pour soi"]
        }
    },
    {
        "meaning": "to fail to pay attention to responsibilities",
        "forms": {
            "spanish": ["estar dormido al volante"],
            "english": ["asleep at the wheel"],
            "french": ["ne pas etre vigilant"]
        }
    },
    {
        "meaning": "to fall asleep lightly",
        "forms": {
            "spanish": ["quedarse dormido"],
            "english": ["doze off"],
            "french": ["s assoupir"]
        }
    },
    {
        "meaning": "to invite problems by behaving recklessly",
        "forms": {
            "spanish": ["buscarse problemas"],
            "english": ["ask for trouble"],
            "french": ["chercher les ennuis"]
        }
    },
    {
        "meaning": "to stop a problem at an early stage",
        "forms": {
            "spanish": ["cortar de raiz"],
            "english": ["nip in the bud"],
            "french": ["etouffer dans l oeuf"]
        }
    },
    {
        "meaning": "to avoid revealing thoughts plans or circumstances",
        "forms": {
            "spanish": ["no soltar prenda"],
            "english": ["keep one's cards close to one's chest", "keep your cards close to your chest"],
            "french": ["cacher son jeu"]
        }
    },
    {
        "meaning": "to be skeptical about whether something is true",
        "forms": {
            "spanish": ["tomalo con pinzas", "tomarlo con pinzas"],
            "english": ["take it with a grain of salt", "take it with a pinch of salt"]
        }
    },
    {
        "meaning": "to forget what one was going to say",
        "forms": {
            "spanish": ["se me fueron las cabras al monte", "se me fue el santo al cielo"],
            "english": ["lose one's train of thought", "lost my train of thought"]
        }
    },
    {
        "meaning": "after being hurt once someone becomes extra cautious",
        "forms": {
            "spanish": ["gato escaldado del agua fria huye"],
            "english": ["once bitten twice shy", "once bitten, twice shy"],
            "french": ["chat echaude craint l eau froide"]
        }
    }
]


def normalize_text(value: str) -> str:
    lowered = value.lower().strip()
    without_accents = "".join(
        character
        for character in unicodedata.normalize("NFKD", lowered)
        if not unicodedata.combining(character)
    )
    without_apostrophes = without_accents.replace("'", " ").replace("’", " ")
    return re.sub(r"[^a-z0-9]+", " ", without_apostrophes).strip()


def normalize_language(value: str) -> str:
    normalized = normalize_text(value)
    return LANGUAGE_ALIASES.get(normalized, normalized or "english")


def surrounding_sentence_text(context_text: str, phrase: str | None) -> str:
    surrounding = re.sub(r"\[[^\]]*\]", " ", context_text)
    if phrase:
        surrounding = re.sub(re.escape(phrase), " ", surrounding, flags=re.IGNORECASE)
    return surrounding


def content_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 2 and token not in STOPWORDS
    }


def infer_target_language(context_text: str, phrase: str | None, requested_language: str) -> str:
    requested = normalize_language(requested_language)
    if requested not in {"auto", "detect", "infer"}:
        return requested

    surrounding = surrounding_sentence_text(context_text, phrase)

    words = set(normalize_text(surrounding).split())
    scores = {
        language: len(words & markers)
        for language, markers in LANGUAGE_MARKERS.items()
    }
    best_language = max(scores, key=scores.get)
    return best_language if scores[best_language] > 0 else "english"


def score_phrase_against_form(phrase: str, idiom_form: str) -> float:
    normalized_phrase = normalize_text(phrase)
    normalized_form = normalize_text(idiom_form)
    if not normalized_phrase or not normalized_form:
        return 0.0
    if normalized_phrase == normalized_form:
        return 1.0
    if normalized_phrase in normalized_form or normalized_form in normalized_phrase:
        shorter = min(len(normalized_phrase), len(normalized_form))
        longer = max(len(normalized_phrase), len(normalized_form))
        return 0.88 + min(0.1, shorter / max(longer, 1) * 0.1)

    phrase_tokens = set(normalized_phrase.split())
    form_tokens = set(normalized_form.split())
    token_score = len(phrase_tokens & form_tokens) / max(len(phrase_tokens | form_tokens), 1)
    sequence_score = SequenceMatcher(None, normalized_phrase, normalized_form).ratio()
    return max(sequence_score, token_score)


def score_phrase_against_meaning(phrase: str, entry: dict[str, Any]) -> float:
    normalized_phrase = normalize_text(phrase)
    if not normalized_phrase:
        return 0.0

    query_tokens = content_tokens(phrase)
    if len(query_tokens) < 2:
        return 0.0

    best_score = 0.0
    for meaning in [entry["meaning"], *entry.get("meaning_aliases", [])]:
        normalized_meaning = normalize_text(meaning)
        meaning_tokens = content_tokens(meaning)
        if not meaning_tokens:
            continue
        overlap = len(query_tokens & meaning_tokens)
        token_score = overlap / max(len(query_tokens | meaning_tokens), 1)
        coverage_score = overlap / max(len(meaning_tokens), 1)
        sequence_score = SequenceMatcher(None, normalized_phrase, normalized_meaning).ratio()
        best_score = max(best_score, token_score, coverage_score * 0.82, sequence_score * 0.9)
    return best_score


def find_database_matches(
    context_text: str,
    phrase: str | None,
    target_language: str,
    limit: int = 2
) -> tuple[list[dict[str, Any]], float, str]:
    query = phrase or context_text
    resolved_target_language = infer_target_language(context_text, phrase, target_language)
    scored_entries: list[tuple[float, dict[str, Any], str, str]] = []

    for entry in IDIOM_DATABASE:
        best_score = 0.0
        best_form = ""
        match_kind = "idiom"
        for forms in entry["forms"].values():
            for idiom_form in forms:
                score = score_phrase_against_form(query, idiom_form)
                if score > best_score:
                    best_score = score
                    best_form = idiom_form
                    match_kind = "idiom"

        meaning_score = score_phrase_against_meaning(query, entry)
        if meaning_score > best_score:
            best_score = meaning_score
            best_form = entry["meaning"]
            match_kind = "meaning"

        threshold = 0.72 if match_kind == "idiom" else 0.66
        if best_score >= threshold:
            scored_entries.append((best_score, entry, best_form, match_kind))

    scored_entries.sort(key=lambda item: item[0], reverse=True)
    suggestions: list[dict[str, Any]] = []
    seen_target_forms: set[str] = set()
    top_score = scored_entries[0][0] if scored_entries else 0.0
    for score, entry, matched_form, match_kind in scored_entries[:limit * 3]:
        if top_score >= 0.92 and score < 0.9:
            continue
        target_forms = entry["forms"].get(resolved_target_language, [])
        for target_form in target_forms[:1]:
            normalized_target_form = normalize_text(target_form)
            if normalized_target_form in seen_target_forms:
                continue
            seen_target_forms.add(normalized_target_form)
            explanation_prefix = "Dictionary idiom match" if match_kind == "idiom" else "Dictionary meaning match"
            suggestions.append({
                "suggested_idiom": target_form,
                "explanation": f"{explanation_prefix} for '{matched_form}': {entry['meaning']}.",
                "confidence_score": round(min(0.99, max(0.72, score)), 2)
            })
        if len(suggestions) >= limit:
            break

    best_match_score = scored_entries[0][0] if scored_entries else 0.0
    return suggestions[:limit], best_match_score, resolved_target_language
