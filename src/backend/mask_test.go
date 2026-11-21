package main

import "testing"

func TestMaskPersonalData(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{"e-mail", "mail: a.b@firma.pl", "mail: [ukryto]"},
		{"pesel with valid checksum", "PESEL 44051401359 koniec", "PESEL [ukryto] koniec"},
		{"pesel written as 6+5 with space", "PESEL 440514 01359", "PESEL [ukryto]"},
		{"pesel written as 6+5 with dash", "PESEL 440514-01359", "PESEL [ukryto]"},
		{"11-digit amount that is not a pesel", "Kwota 12345678901 sztuk", "Kwota 12345678901 sztuk"},
		{"11 digits with a valid checksum but a bad month", "numer 44131401357", "numer 44131401357"},
		{"polish mobile with spaces", "tel 600 700 800", "tel [ukryto]"},
		{"polish mobile contiguous", "tel 600700800", "tel [ukryto]"},
		{"polish mobile with dots", "tel 600.100.200", "tel [ukryto]"},
		{"polish mobile with dashes", "tel 600-700-800", "tel [ukryto]"},
		{"international with dashes", "tel +48 600-700-800", "tel [ukryto]"},
		{"international polish", "tel +48 600 700 800", "tel [ukryto]"},
		{"international us", "call +1 202 555 0143 now", "call [ukryto] now"},
		{"international german", "Tel. +49 30 12345678", "Tel. [ukryto]"},
		{"international with 00 prefix", "tel 0048 600 700 800", "tel [ukryto]"},
		{"polish landline", "biuro (22) 123 45 67", "biuro [ukryto]"},
		{"spaced iban", "konto PL61 1090 1014 0000 0712 1981 2874", "konto [ukryto]"},
		{"unspaced iban with prefix", "konto PL61109010140000071219812874.", "konto [ukryto]."},
		{"bare 26-digit iban", "konto 61109010140000071219812874", "konto [ukryto]"},
		{"amount with spaced thousands in zloty", "wydano 100 000 000 zł", "wydano 100 000 000 zł"},
		{"amount in billions", "10 000 000 000 zł", "10 000 000 000 zł"},
		{"amount in zloty looks like a mobile", "kwota 123 456 789 zł", "kwota 123 456 789 zł"},
		{"amount starting like a mobile", "kwota 600 000 000 zł", "kwota 600 000 000 zł"},
		{"amount with a magnitude word", "10 mld zł", "10 mld zł"},
		{"amount in millions", "to 600 700 800 mln", "to 600 700 800 mln"},
		{"amount in euro", "to 600 700 800 EUR", "to 600 700 800 EUR"},
		{"percentage", "wzrost 600 700 800 %", "wzrost 600 700 800 %"},
		{"iso date", "2024-11-21", "2024-11-21"},
		{"iso date followed by a digit", "2024-11-21 5", "2024-11-21 5"},
		{"dotted date", "21.11.2024", "21.11.2024"},
		{"big number split in thousands without prefix", "5 000 000 000 000 osób", "5 000 000 000 000 osób"},
		{"year and percent", "W 2026 roku wzrost o 12,5 proc", "W 2026 roku wzrost o 12,5 proc"},
		{"plain text", "Polska jest w UE od 2004 roku", "Polska jest w UE od 2004 roku"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if got := maskPersonalData(test.input); got != test.want {
				t.Errorf("maskPersonalData(%q) = %q, want %q", test.input, got, test.want)
			}
		})
	}
}

func TestIsValidPesel(t *testing.T) {
	tests := map[string]bool{
		"44051401359": true,
		"44051401358": false,
		"44131401357": false,
		"4405140135":  false,
	}
	for candidate, want := range tests {
		if got := isValidPesel(candidate, 0, len(candidate)); got != want {
			t.Errorf("isValidPesel(%q) = %v, want %v", candidate, got, want)
		}
	}
}
