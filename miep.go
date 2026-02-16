package main

import (
	"bufio"
	"fmt"
	"math/rand"
	"os"
	"strconv"
	"strings"
	"time"
)

// MiepInterpreter represents the MIEP interpreter state
type MiepInterpreter struct {
	variables [26]int16           // A-Z variables
	memory    [65536]byte         // 64KB memory
	pbuff     string              // Program buffer
	psize     int                 // Program size
	s         string              // Current parsing string
	pos       int                 // Current position in string
	ln        int                 // Current line number
	stack     []interface{}       // Runtime stack
	sp        int                 // Stack pointer
	tron      bool                // Trace mode
	mod       int16               // Modulo result
	forMode   int                 // FOR loop mode
	reader    *bufio.Reader       // Standard input reader
}

// NewInterpreter creates a new MIEP interpreter
func NewInterpreter() *MiepInterpreter {
	return &MiepInterpreter{
		reader: bufio.NewReader(os.Stdin),
		stack:  make([]interface{}, 0, 65536),
	}
}

// currentChar returns the current character
func (m *MiepInterpreter) currentChar() byte {
	if m.pos < len(m.s) {
		return m.s[m.pos]
	}
	return 0
}

// advance moves the position forward
func (m *MiepInterpreter) advance(count int) {
	m.pos += count
}

// peek looks ahead in the string
func (m *MiepInterpreter) peek(offset int) byte {
	if m.pos+offset < len(m.s) {
		return m.s[m.pos+offset]
	}
	return 0
}

// skipSpaces skips whitespace characters
func (m *MiepInterpreter) skipSpaces() {
	for m.currentChar() == ' ' {
		m.advance(1)
	}
}

// syntaxError reports a syntax error
func (m *MiepInterpreter) syntaxError() {
	fmt.Printf("\nSyntaxerror in %d", m.ln)
	os.Stdout.Sync()
}

// skipChar skips an expected character
func (m *MiepInterpreter) skipChar(c byte) {
	if m.currentChar() == c {
		m.advance(1)
		return
	}
	m.syntaxError()
}

// isAlpha checks if character is alphabetic
func isAlpha(c byte) bool {
	return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
}

// isDigit checks if character is a digit
func isDigit(c byte) bool {
	return c >= '0' && c <= '9'
}

// isXDigit checks if character is a hex digit
func isXDigit(c byte) bool {
	return isDigit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F')
}

// toUpper converts character to uppercase
func toUpper(c byte) byte {
	if c >= 'a' && c <= 'z' {
		return c - 'a' + 'A'
	}
	return c
}

// getOperator2 gets binary operator
func (m *MiepInterpreter) getOperator2() byte {
	c := m.currentChar()
	switch c {
	case '=', '+', '-', '*', '/':
		m.advance(1)
		return c
	case '<':
		m.advance(1)
		if m.currentChar() == '>' {
			m.advance(1)
			return 'N' // Not equal
		} else if m.currentChar() == '=' {
			m.advance(1)
			return 'A' // Less than or equal
		}
		return '<'
	case '>':
		m.advance(1)
		if m.currentChar() == '=' {
			m.advance(1)
			return 'B' // Greater than or equal
		}
		return '>'
	default:
		return 0
	}
}

// getOperator1 gets unary operator
func (m *MiepInterpreter) getOperator1() byte {
	c := m.currentChar()
	switch c {
	case '+', '-', '\'', '#', '%':
		m.advance(1)
		return c
	default:
		return 0
	}
}

// getVariable gets variable name
func (m *MiepInterpreter) getVariable() byte {
	c := byte(0)
	if isAlpha(m.currentChar()) {
		c = m.currentChar()
		for m.pos < len(m.s) && isAlpha(m.s[m.pos]) {
			m.advance(1)
		}
	}
	return c
}

// getHexValue parses hexadecimal number
func (m *MiepInterpreter) getHexValue() int16 {
	if !isXDigit(m.currentChar()) {
		return -1
	}
	start := m.pos
	for isXDigit(m.currentChar()) {
		m.advance(1)
	}
	val, _ := strconv.ParseInt(m.s[start:m.pos], 16, 32)
	return int16(val)
}

// getDecimalValue parses decimal number
func (m *MiepInterpreter) getDecimalValue() int16 {
	if !isDigit(m.currentChar()) {
		return -1
	}
	start := m.pos
	for isDigit(m.currentChar()) {
		m.advance(1)
	}
	val, _ := strconv.Atoi(m.s[start:m.pos])
	return int16(val)
}

// getString parses string literal
func (m *MiepInterpreter) getString() string {
	result := ""
	if m.currentChar() == '"' {
		m.skipChar('"')
		for m.currentChar() != '"' && m.currentChar() != 0 {
			result += string(m.currentChar())
			m.advance(1)
		}
		m.skipChar('"')
	}
	return result
}

// getConstant parses constant value
func (m *MiepInterpreter) getConstant() int16 {
	if m.currentChar() == '"' {
		s := m.getString()
		v := int16(0)
		if len(s) > 0 {
			v = int16(s[0])
		}
		if len(s) > 1 {
			v += int16(s[1]) * 256
		}
		return v
	} else if m.currentChar() == '$' {
		m.skipChar('$')
		return m.getHexValue()
	} else if isDigit(m.currentChar()) {
		return m.getDecimalValue()
	}
	return 0
}

// term parses a term (operand)
func (m *MiepInterpreter) term() int16 {
	var v int16
	var c byte

	m.skipSpaces()

	// Parenthesized expression
	if m.currentChar() == '(' {
		m.skipChar('(')
		v = m.expression()
		m.skipSpaces()
		m.skipChar(')')
		return v
	}

	// Variable
	c = m.getVariable()
	if c != 0 {
		varIdx := toUpper(c) - 'A'

		// Array access V:exp)
		if m.currentChar() == ':' {
			m.skipChar(':')
			v = m.expression()
			m.skipChar(')')
			return int16(m.memory[m.variables[varIdx]+v])
		} else if m.currentChar() == '(' {
			// Word array access V(exp)
			m.skipChar('(')
			v = m.expression()
			m.skipChar(')')
			addr := m.variables[varIdx] + v*2
			return int16(m.memory[addr]) | (int16(m.memory[addr+1]) << 8)
		} else {
			// Simple variable
			return m.variables[varIdx]
		}
	}

	// Getch - read single character
	if m.currentChar() == '$' && !isXDigit(m.peek(1)) {
		m.advance(1)
		c, _ := m.reader.ReadByte()
		return int16(c)
	}

	// Input
	if m.currentChar() == '?' {
		m.advance(1)
		line, _ := m.reader.ReadString('\n')
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "$") {
			val, _ := strconv.ParseInt(line[1:], 16, 32)
			return int16(val)
		}
		val, _ := strconv.Atoi(line)
		return int16(val)
	}

	// Constant
	savedPos := m.pos
	v = m.getConstant()
	if v != 0 || m.pos != savedPos {
		return v
	}

	// Unary operator
	c = m.getOperator1()
	if c != 0 {
		v = m.term()
		switch c {
		case '-':
			return -v
		case '+':
			if v < 0 {
				return -v
			}
			return v
		case '#':
			if v != 0 {
				return 0
			}
			return 1
		case '\'':
			if v > 0 {
				return int16(rand.Intn(int(v)))
			}
			return 0
		case '%':
			return m.mod
		}
	}

	return 0
}

// expression parses an expression
func (m *MiepInterpreter) expression() int16 {
	var v, v2 int16
	var c byte

	m.skipSpaces()
	v = m.term()

	for {
		c = m.getOperator2()
		if c == 0 {
			break
		}

		v2 = m.term()

		switch c {
		case '+':
			v += v2
		case '-':
			v -= v2
		case '*':
			v *= v2
		case '/':
			if v2 == 0 {
				fmt.Println("Division by zero")
				v = -1
			} else {
				m.mod = v % v2
				v /= v2
			}
		case '=':
			if v == v2 {
				v = 1
			} else {
				v = 0
			}
		case '<':
			if v < v2 {
				v = 1
			} else {
				v = 0
			}
		case 'N':
			if v != v2 {
				v = 1
			} else {
				v = 0
			}
		case 'A':
			if v <= v2 {
				v = 1
			} else {
				v = 0
			}
		case '>':
			if v > v2 {
				v = 1
			} else {
				v = 0
			}
		case 'B':
			if v >= v2 {
				v = 1
			} else {
				v = 0
			}
		}
	}

	return v
}

// skipToNewline skips to end of line
func (m *MiepInterpreter) skipToNewline() {
	for m.currentChar() != '\n' && m.currentChar() != 0 {
		m.advance(1)
	}
	if m.currentChar() == '\n' {
		m.advance(1)
	}
}

// searchLine searches for line number in program
func (m *MiepInterpreter) searchLine(targetLine int16) int16 {
	m.s = m.pbuff
	m.pos = 0

	// Skip comment line
	if len(m.s) > 0 && m.s[0] == '#' {
		for m.currentChar() != '\n' {
			m.advance(1)
		}
		m.advance(1)
	}

	for m.pos < len(m.s) {
		savedPos := m.pos
		lineNum := m.getDecimalValue()

		if lineNum == -1 {
			return -1
		}

		if lineNum >= targetLine {
			m.pos = savedPos
			return lineNum
		}

		m.skipToNewline()
	}

	return -1
}

// gotoLine jumps to a line number
func (m *MiepInterpreter) gotoLine(lineNum int16) {
	if lineNum == -1 {
		m.ln = -1
	} else {
		m.ln = int(m.searchLine(lineNum))
	}
}

// gosub calls a subroutine
func (m *MiepInterpreter) gosub(lineNum int16) {
	m.stack = append(m.stack, m.s)
	m.stack = append(m.stack, m.pos)
	m.sp += 2
	m.gotoLine(lineNum)
}

// returnFromSub returns from subroutine
func (m *MiepInterpreter) returnFromSub() {
	if m.sp >= 2 {
		m.sp -= 2
		m.pos = m.stack[m.sp+1].(int)
		m.s = m.stack[m.sp].(string)
		m.stack = m.stack[:m.sp]
	}
}

// doLoop starts a DO loop
func (m *MiepInterpreter) doLoop() {
	m.stack = append(m.stack, m.s)
	m.stack = append(m.stack, m.pos)
	m.sp += 2
}

// untilLoop UNTIL condition
func (m *MiepInterpreter) untilLoop() {
	if m.sp >= 2 {
		m.sp -= 2
		savedPos := m.stack[m.sp+1].(int)
		savedS := m.stack[m.sp].(string)
		m.stack = m.stack[:m.sp]

		v := m.expression()
		if v == 0 {
			m.s = savedS
			m.pos = savedPos
			m.stack = append(m.stack, savedS)
			m.stack = append(m.stack, savedPos)
			m.sp += 2
		}
	}
}

// nextLoop NEXT in FOR loop
func (m *MiepInterpreter) nextLoop() {
	if m.sp >= 3 {
		m.sp -= 3
		toVal := m.stack[m.sp+2].(int16)
		savedPos := m.stack[m.sp+1].(int)
		savedS := m.stack[m.sp].(string)
		varIdx := m.stack[m.sp-1].(int)
		m.sp--
		m.stack = m.stack[:m.sp]

		v := m.expression()
		m.variables[varIdx] = v

		if v <= toVal {
			m.s = savedS
			m.pos = savedPos
			m.stack = append(m.stack, varIdx)
			m.stack = append(m.stack, savedS)
			m.stack = append(m.stack, savedPos)
			m.stack = append(m.stack, toVal)
			m.sp += 4
		}
	}
}

// ifStatement IF statement
func (m *MiepInterpreter) ifStatement(condition int16) {
	if condition == 0 {
		m.skipToNewline()
		m.pos--
	}
}

// loadSource loads source file
func (m *MiepInterpreter) loadSource(filename string) error {
	data, err := os.ReadFile(filename)
	if err != nil {
		return err
	}
	m.pbuff = string(data)
	m.psize = len(m.pbuff)
	return nil
}

// loadSourceCommand loads source from command
func (m *MiepInterpreter) loadSourceCommand() {
	m.skipSpaces()
	start := m.pos
	for m.currentChar() != '\n' {
		m.advance(1)
	}
	filename := m.s[start:m.pos]
	m.loadSource(filename)
}

// optionalCommand executes optional command
func (m *MiepInterpreter) optionalCommand() {
	c1 := toUpper(m.currentChar())
	m.advance(1)
	c2 := toUpper(m.currentChar())
	m.advance(1)

	if c1 == 'L' && c2 == 'D' {
		m.loadSourceCommand()
	} else if c1 == 'Q' && c2 == 'U' {
		os.Exit(0)
	} else if c1 == 'T' && c2 == 'N' {
		m.tron = true
	} else if c1 == 'T' && c2 == 'F' {
		m.tron = false
	} else if c1 == 'S' && c2 == 'H' {
		// Shell - not implemented for security
		fmt.Println("Shell command not supported")
	} else if c1 == 'F' && c2 == 'M' {
		v := m.expression()
		m.forMode = int(v)
	} else {
		m.syntaxError()
	}
}

// run executes the program
func (m *MiepInterpreter) run() {
	for {
		c := m.currentChar()

		if c == 0 {
			return
		}

		if m.ln == -1 {
			return
		}

		// Parse line number
		if m.ln != 0 {
			v := m.getDecimalValue()
			if m.tron {
				fmt.Printf("[%d]", v)
				os.Stdout.Sync()
			}
			m.ln = int(v)

			if m.currentChar() != ' ' {
				m.skipToNewline()
				continue
			}
		}

		// Execute statements
		for {
			c = m.currentChar()

			if c == 0 {
				return
			} else if c == '\n' {
				m.advance(1)
				break
			} else if c == ' ' {
				m.skipSpaces()
				continue
			} else if c == '"' {
				// String literal - print
				fmt.Print(m.getString())
				os.Stdout.Sync()
				continue
			} else if c == '/' {
				// Newline
				m.skipChar('/')
				fmt.Println()
				continue
			} else if c == '.' {
				// Print spaces
				m.skipChar('.')
				m.skipChar('=')
				v := m.expression()
				for i := int16(0); i < v; i++ {
					fmt.Print(" ")
				}
				os.Stdout.Sync()
				continue
			} else if c == '*' {
				// Optional command
				m.advance(1)
				m.optionalCommand()
				continue
			} else if c == '?' {
				// Output commands
				m.advance(1)
				c = m.currentChar()

				if c == '=' {
					// Print decimal
					m.skipChar('=')
					v := m.expression()
					fmt.Print(int(v))
					os.Stdout.Sync()
				} else if c == '?' {
					// Print hex (4 digits)
					m.skipChar('?')
					m.skipChar('=')
					v := m.expression()
					fmt.Printf("%04x", uint16(v))
					os.Stdout.Sync()
				} else if c == '$' {
					// Print hex (2 digits)
					m.skipChar('$')
					m.skipChar('=')
					v := m.expression()
					fmt.Printf("%02x", uint8(v))
					os.Stdout.Sync()
				} else if c == '(' {
					// Formatted print
					m.skipChar('(')
					width := m.expression()
					m.skipChar(')')
					m.skipChar('=')
					v := m.expression()
					format := fmt.Sprintf("%%%dd", width)
					fmt.Printf(format, int(v))
					os.Stdout.Sync()
				} else {
					m.syntaxError()
					return
				}
				continue
			} else if c == '\'' {
				// Random seed
				m.advance(1)
				m.skipChar('=')
				v := m.expression()
				rand.Seed(int64(v))
				continue
			} else if c == '$' {
				// Print character
				m.advance(1)
				m.skipChar('=')
				v := m.expression()
				fmt.Printf("%c", byte(v))
				os.Stdout.Sync()
				continue
			} else if c == '#' {
				// GOTO
				m.advance(1)
				m.skipChar('=')
				v := m.expression()
				m.gotoLine(v)
				break
			} else if c == '!' {
				// GOSUB
				m.advance(1)
				m.skipChar('=')
				v := m.expression()
				m.gosub(v)
				break
			} else if c == ']' {
				// RETURN
				m.advance(1)
				m.returnFromSub()
				continue
			} else if c == '@' {
				// DO/UNTIL/NEXT
				m.advance(1)
				if m.currentChar() == '=' {
					m.skipChar('=')
					if m.currentChar() == '(' {
						// UNTIL
						m.untilLoop()
					} else {
						// NEXT
						m.nextLoop()
					}
				} else {
					// DO
					m.doLoop()
				}
				continue
			} else if c == ';' {
				// IF
				m.advance(1)
				m.skipChar('=')
				v := m.expression()
				m.ifStatement(v)
				continue
			} else if isAlpha(c) {
				// Variable assignment
				varChar := m.getVariable()
				varIdx := int(toUpper(varChar) - 'A')

				if m.currentChar() == ':' {
					// Byte array assignment
					m.advance(1)
					idx := m.expression()
					m.skipChar(')')
					m.skipChar('=')
					v := m.expression()
					m.memory[m.variables[varIdx]+idx] = byte(v)
				} else if m.currentChar() == '(' {
					// Word array assignment
					m.advance(1)
					idx := m.expression()
					m.skipChar(')')
					m.skipChar('=')
					v := m.expression()
					addr := m.variables[varIdx] + idx*2
					m.memory[addr] = byte(v)
					m.memory[addr+1] = byte(v >> 8)
				} else {
					// Simple variable assignment
					m.skipChar('=')
					v := m.expression()
					m.variables[varIdx] = v
				}

				// FOR loop
				if m.currentChar() == ',' {
					m.skipChar(',')
					toVal := m.expression()
					v := m.variables[varIdx]

					if v > toVal && m.forMode != 0 {
						// Skip to @=
						eof := false
						for m.currentChar() != '@' {
							if m.currentChar() == 0 {
								eof = true
								break
							}
							m.advance(1)
						}

						if !eof {
							m.skipChar('@')
							m.skipChar('=')
							m.expression()
						}
					} else {
						m.stack = append(m.stack, varIdx)
						m.stack = append(m.stack, m.s)
						m.stack = append(m.stack, m.pos)
						m.stack = append(m.stack, toVal)
						m.sp += 4
					}
				}
				continue
			}

			m.syntaxError()
			return
		}
	}
}

func main() {
	rand.Seed(time.Now().UnixNano())

	if len(os.Args) >= 2 {
		interp := NewInterpreter()
		err := interp.loadSource(os.Args[1])
		if err != nil {
			fmt.Printf("Error loading file: %v\n", err)
			os.Exit(1)
		}
		interp.gotoLine(1)
		interp.run()
	} else {
		fmt.Println("Usage: miep file")
	}
}
